# -*- coding: utf-8 -*-
#Python
import uvicorn
import uuid
from typing import Optional, List
from datetime import datetime
import pandas as pd
import jwt
import secrets

#Models
from classmodels.models import *

#fastAPI
from fastapi import FastAPI, Body, Query, Path, Depends, Header
from fastapi.middleware.cors import CORSMiddleware

#Database
from config.db import conn
from schemas.dbtables import dbusers,dbpersons,dbregister, dbpool, dbmassive, dbmessages

#Auth
from auth.authjwt import signJWT, decodeJWT, JWTBearer
from decouple import config



#API CONFIGURATION------------------------------------------------------------------------------
#=================================================================================
app=FastAPI()

#CORS
app.add_middleware(CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'])
#HOME====================================================================
@app.get("/")
def home():
    return {"hello":"SoMoƧ"}

@app.get("/users", status_code=200) #vista de usuarios
async def view_user(username: str = Query(default=None)): #recibimos un usuario por query para consultarlo
    
    if username:
        resp=conn.execute("SELECT * FROM dbusers WHERE username='%s'"%username).fetchall()
    else:
        resp=conn.execute("SELECT * FROM dbusers").fetchall()
    return resp

#REGISTRO DE NUEVO USUARIO ====================================================================================================
@app.post("/users/new", status_code=201) #Registro de nuevo usuario
async def new_user(user: User = Body(...)): #recibimos un usuario desde un json
    new_user={
        "id":user.user_id,
        "created":datetime.now(),
        "name":user.name,
        "username":user.username,
        "password":user.password,
        "contact":user.contact,
        "location":user.location,
        "leftpromo": 100000,
        "isactive":1}

    conn.execute(dbusers.insert().values(new_user))
    return {"message":"Usuario creado", "user_id":signJWT(user.user_id)}


@app.post("/login") 
async def loginuser(username: str = Body(...), password: str = Body(...)):

    resp=conn.execute(dbusers.select().where(dbusers.c.username==username)).first()

    #resp=conn.execute("SELECT id, username, password, isactive FROM dbusers WHERE username='%s'"%username).first()
    if resp:
        if secrets.compare_digest(resp['password'],password):
            if resp['isactive']==1:
                return {"message":"¡Has iniciado sesion!", "user_id": signJWT(resp["id"])}
            else:
                return {"message":"Regulariza tu pago para continuar"}
    else:
        return {"message": "Usuario incorrecto o inexistente"}


@app.post("/{master_id}/suscribe")
async def pay(username: str = Body(...)):
    conn.execute("UPDATE dbusers SET isactive=1, leftpromo=100000 WHERE username='%s'"%username)
    return {"message": "Suscrito"}

@app.post("/unsuscribe", dependencies=[Depends(JWTBearer(()))])
async def unsuscribe(authorization = Header(...)):
    decoded_token=decodeJWT(authorization.replace("Bearer ",""))
    user_id=decoded_token["user_id"]

    conn.execute("UPDATE dbusers SET isactive=0, leftpromo=0 WHERE id='%s'"%user_id)
    return {"message": "Desuscrito"}


# REGISTRO DE PERSONAS CLIENTES DEL USUARIO =======================================================================================
@app.post("/register",status_code=201, dependencies=[Depends(JWTBearer(()))]) #nuevos registros y tabla de espera
async def new_register(register: Register = Body(...), authorization = Header(...)):
    
    decoded_token=decodeJWT(authorization.replace("Bearer ",""))
    user_id=decoded_token["user_id"]
    
    # Datos necesarios para llenar la tabla dbregister
    new_register={
        "id":register.register_id,
        "created":datetime.now(),
        "user_id":user_id,
        "service":register.service,
        "dispatched":register.dispatched}

    #consulta DB para obtener el nombre del telefono reigstrado y saber si se tienen los datos de esa persona
    resp=conn.execute("SELECT phone, name FROM dbpersons"\
        " WHERE dbpersons.phone NOT IN(SELECT phone FROM dbpool) AND dbpersons.phone = '%s'"%register.phone).first()

    if resp : #si existe la persona registrada se suma 1 a sus visitas globales (visitas sin importar a que usuario fue)
        new_register["person_id"]=resp["phone"] #
        
        if resp["name"]==register.name: #comprueba si el nombre de registro coincide con el nombre dado
            conn.execute(dbpersons.update(dbpersons.c.phone == resp["phone"]).values(visits=dbpersons.c.visits + 1))

        else: #si el nombre no coincide actualiza los datos
            conn.execute(dbpersons.update(dbpersons.c.phone == resp["phone"]).values(
                name=register.name,
                gender=register.gender,
                agerange=register.agerange,
                visits = 1))

    else: #si no existe la persona la crea en la base de personas

        new_register["person_id"]=register.phone
        new_person={
            "phone":register.phone,
            "name":register.name,
            "gender":register.gender,
            "agerange":register.agerange,
            "visits":register.visits}
        
        conn.execute(dbpersons.insert().values(new_person)) #inserta la nueva persona en dbpersons

    conn.execute(dbregister.insert().values(new_register)) #inserta el nuevo registro en dbregister
    
    # INICIA SECUENCIA DE ENVIO DE MENSAJES************************
    if register.dispatched!='SERVED': #dispatched = 'WAITING' es que va a pool
        
        to_pool={
            "phone":register.phone, # person_id necesario para arduino
            "text":register.text, # necesario para arduino y parte principal del servicio se obtiene de la consulta anterior
            "register_id":new_register["id"],  # registro que esta asociado a la espera
            "done":"STANDBY"} # estado en que se encuentra en stanby 

        try:
            conn.execute(dbpool.insert().values(to_pool)) #en pool se espera a que ocurra el intercambio de sms
        except:
            return {'message':'Este telefono ya está asociado a otra persona'}

        new_register['name']=register.name #añade el nombre para ponerlo en la lista de espera
        return new_register # retorna el nuevo registro que se añadirá a los registros previos guardados en el frontend
    else:
        conn.execute(dbregister.update().filter(dbregister.c.id==register.register_id, dbregister.c.user_id==user_id).values(dispatchedat=datetime.now()))
        return {'name':''}

@app.get("/register",status_code=200, dependencies=[Depends(JWTBearer(()))])
async def get_register(authorization = Header(...),
    querycreated: Optional[datetime] = Query(None), 
    queryperson_id: Optional[str] = Query(None, regex="\d{10}"),
    queryservice: Optional[str] = Query(None),
    querydispatched: Optional[List[str]] = Query(None),
    querydispatchedat: Optional[datetime] = Query(None)):

    decoded_token=decodeJWT(authorization.replace("Bearer ",""))
    user_id=decoded_token["user_id"]

    resp=conn.execute("SELECT dbregister.*, dbpersons.name FROM dbregister INNER JOIN dbpersons ON dbregister.person_id = dbpersons.phone"\
        " AND dbregister.user_id='%s' ORDER BY dbregister.created DESC" %user_id).fetchall()
    
    if len(resp)>0:
    
        if querycreated or queryperson_id or queryservice or querydispatched or querydispatchedat:
            resp=pd.DataFrame(resp)
            resp.columns=["id","created","person_id","user_id","service","dispatched","dispatchedat","name"]

            if queryperson_id:
                resp=resp[((resp["person_id"] == queryperson_id) & (resp["person_id"].notnull())) ]
            if queryservice:
                resp=resp[(resp["service"] == queryservice) & (resp["service"].notnull())]
            if querydispatched:
                resp=resp[(resp["dispatched"].isin(querydispatched)) & (resp["dispatched"].notnull())]
            if querycreated:
                resp=resp[(resp["created"] >= querycreated) & (resp["created"].notnull())]
            if querydispatchedat:
                resp=resp[(resp["dispatchedat"] >= querydispatchedat) & (resp["dispatchedat"].notnull())]
                resp=resp.sort_values(by=['dispatchedat'], ascending=False)
            
            return resp.to_dict("records")
    else:
        return resp

@app.put("/register", dependencies=[Depends(JWTBearer(()))])
async def serev_register(register_id = Body(...), authorization=Header(...)):

    decoded_token=decodeJWT(authorization.replace("Bearer ",""))
    user_id=decoded_token["user_id"]

    conn.execute(dbregister.update().filter(dbregister.c.id==register_id, dbregister.c.user_id==user_id).values(dispatched='SERVED', dispatchedat=datetime.now()))
    try:
        conn.execute(dbpool.delete().where(dbpool.c.register_id==register_id))
    except:
        pass

    return {"message":"SERVIDO"}


# AÑADIR A LA COLA DE SMS DESDE EL FRONTEND ===================================================================================
# esta funcion se ejecuta al presionar el boton NOTIFY en el frontend y manda el registro a la cola de sms
# target una lista de clase TARGET que se manda del frontend aprovechando los datos de la lista de espera
@app.post("/notify",status_code=202, dependencies=[Depends(JWTBearer(()))])
async def notify_wait(register_id = Body(...)):
    conn.execute(dbpool.update().filter(dbpool.c.done=="STANDBY", dbpool.c.register_id==register_id).values(done='WAITING'))
    conn.execute(dbregister.update().filter(dbregister.c.dispatched=="WAITING", dbregister.c.id==register_id).values(dispatched='SENDING'))
    #conn.execute("UPDATE dbpool SET done='WAITING' WHERE done = 'STANDBY' AND register_id='%s'"%register_id)
    return {"message": "NOTIFICADO","register_id":register_id}


@app.post("/cancelwait",status_code=202, dependencies=[Depends(JWTBearer(()))])
async def notify_wait(register_id = Body(...)):
    conn.execute(dbpool.delete().where(dbpool.c.register_id==register_id))
    conn.execute(dbregister.update().where(dbregister.c.id == register_id).values(dispatched='CANCELED', dispatchedat=datetime.now()))
    return {"message": "CANCELADO","register_id":register_id}


# FUNCION PARA PEDIR PETICION DE SMS A POOL ================================================================================================
# JALA TODOS LAS PETICIONES DE MENSAJE QUE DEJARON DE SER STANDBY PORQUE SE PRESIONÓ EL BOTÓN NOTIFY
# ESTA FUNCION LEE LOS MENSAJES QUE DEBEN ENVIARSE Y PONE EL ESTADO DE POOL DE done = 0 (esperando ser leido) a done = 1 (leido y esperando confirmacion de envío exitoso)
@app.get("/{master_id}/pool") 
async def getpool(master_id: str = Path(...)):
    if master_id==config("SU"):

        resp=conn.execute("SELECT phone, text, register_id FROM dbpool WHERE done = 'WAITING'").fetchall()
        if resp:
            ids=','.join(["'"+r.phone+"'" for r in resp])
            conn.execute(f"UPDATE dbpool SET done = 'SENDING' WHERE phone IN ({ids})")
        
        return resp #estos datos serán leidos por el script que los enviará al arduino
    else:
        return {"message":"No tiene permisos"}


# ACTUALIZAR POOL CUANDO EL MENSAJE FUE ENVIADO Y ACTUALIZAR LAS RESPUESTAS DE LOS USUARIOS
# Esta funcion se usa cuando hay una lista de numeros que han dado OK en respuesta del arduino en el envio de mensajes
# Recibe la lista de numeros y actualiza el pool como numeros que ya han sido notificados para que al siguiente request no aparezcan
# Recibe una lista de las respuestas que dieron las personas al SMS (OK, CANCELAR) y es actualiada la lista de espera del frontend
# el master_id es un path especial al que solo SOMOS puede acceder para enviar mensajes y ejecutar funciones de administrador
@app.post("/{master_id}/pool") 
async def updatepool(master_id: str = Path(...), target: List[str] = Body(default=None)): #responses: List[Response]=Body(default=None)

    if master_id==config("SU"):

        #target es una lista de register_id que tienen que ser actualizados en el pool (done=2) dado que el SMS fue enviado con exito
        if target:
            conn.execute(dbregister.update().where(dbregister.c.id.in_(target)).values(dispatched='NOTIFIED'))
            conn.execute(dbpool.delete().where(dbpool.c.register_id.in_(target)))
                    
        return {"message":"Mensajes enviados"}
    else:
        return {"message":"No tiene permisos"}

@app.put("/{master_id}/pool") 
async def updateerrorpool(master_id: str = Path(...), target: List[str] = Body(default=None)): #responses: List[Response]=Body(default=None)

    if master_id==config("SU"):

        # funcion para devolver a la lista de espera los mensajes que hayan marcado error en los modulos
        if target:
            conn.execute(dbpool.update().filter(dbpool.c.done=='SENDING', dbpool.c.register_id.in_(target)).values(done='WAITING'))
                    
        return {"message":"Error al notificar a "+str(target)+", se realizará otro intento"}
    else:
        return {"message":"No tiene permisos"}


# FUNCION PARA PEDIR PETICION DE SMS A MASSIVE ================================================================================================
@app.get("/{master_id}/massive") 
async def getmassive(master_id: str = Path(...)):

    if master_id==config("SU"):

        resp=conn.execute("SELECT t.id, t.phone, dbpersons.name, t.text FROM "\
        "(SELECT dbmassive.id, dbmassive.phone, dbmessages.text FROM somosdb.dbmassive "\
            "INNER JOIN somosdb.dbmessages ON dbmassive.message_id=dbmessages.id WHERE dbmassive.done='WAITING') "\
                "AS t INNER JOIN somosdb.dbpersons ON t.phone=dbpersons.phone LIMIT 100").fetchall()
        if resp:
            ids=','.join(["'"+r.id+"'" for r in resp])
            conn.execute(f"UPDATE dbmassive SET done = 'SENDING' WHERE id IN ({ids})")
      
        return resp #estos datos serán leidos por el script que los enviará al arduino
    else:
        return {"message":"No tiene permisos"}


# SECCION DE ENVIO MASIVO DE MENSAJE ==========================================================================================
@app.post("/massive",status_code=202, dependencies=[Depends(JWTBearer(()))])
async def notify_many(authorization: str = Header(...), 
target: TargetMassive = Body(...)):

    decoded_token=decodeJWT(authorization.replace("Bearer ",""))
    user_id = decoded_token["user_id"]
    
    to_massive=[]

    resp=conn.execute("SELECT leftpromo FROM dbusers WHERE id='%s'"%user_id).first()

    if target.toall:
        persons = conn.execute("SELECT dbpersons.* FROM dbregister INNER JOIN dbpersons ON"\
        "  dbregister.person_id = dbpersons.phone AND dbregister.user_id='%s' GROUP BY dbpersons.phone" %user_id)
        for person in persons:
            to_massive.append({"id":uuid.uuid4(), "phone": person.phone, "message_id":target.message_id, "user_id":user_id , "done":"WAITING"})
        conn.execute(dbmassive.insert().values(to_massive))
        return {'message':'Se están enviando '+str(len(to_massive))+' mensajes.'}
    
    else:
        if resp.leftpromo>0:
            if resp.leftpromo>=len(target.phones):
        
                persons = conn.execute(dbpersons.select().where(dbpersons.c.phone.in_(target.phones))).fetchall()
                
                for person in persons:
                    to_massive.append({"id":uuid.uuid4(), "phone": person.phone, "message_id":target.message_id, "done":"WAITING"})
                conn.execute(dbmassive.insert().values(to_massive))
                return {'message':'Se están enviando '+str(len(to_massive))+' mensajes.'}
            else:
                return {'message':'Sobrepasas en '+str(len(target.phones)-resp.leftpromo)+' tus mensajes restantes. Disminuye los mensajes o contactanos para conseguir más.'}
        else:
            return {'message':'Agotaste los mensajes de este mes. Contactanos para conseguir más.'}


@app.put("/{master_id}/massive") 
async def updatemassive(master_id: str = Path(...), 
target: List[str] = Body(default=None), errortarget: List[str] = Body(default=None)):

    if master_id==config("SU"):
        
        if target:
            sent=','.join(["'"+ r +"'" for r in target])
            conn.execute("UPDATE dbusers INNER JOIN (SELECT user_id, COUNT(user_id) as sent FROM somosdb.dbmassive"\
		        f" WHERE id IN ({sent}) GROUP BY user_id) AS t ON dbusers.id = t.user_id"\
                " SET dbusers.leftpromo = dbusers.leftpromo-t.sent WHERE dbusers.id = t.user_id;")
        
            conn.execute(dbmassive.delete().filter(dbmassive.c.done=='SENDING', dbmassive.c.id.in_(target)))

        if errortarget:
            conn.execute(dbmassive.update().filter(dbmassive.c.done=='SENDING', dbmassive.c.id.in_(errortarget)).values(done='WAITING'))   
        return {"message":"Mensajes enviados: "+str(len(target))+ "\nMensajes no enviados: "+str(len(errortarget))}
    else:
        return {"message":"No tiene permisos"}


#VISTA TABLA DE PERSONAS ====================================================================================================
#Muestra a todas las personas que han sido clientes de un usuario y las muestra segun el filtro seleccionado
@app.get("/persons", dependencies=[Depends(JWTBearer(()))])
async def view_person(authorization: str = Header(...),
    queryphone: Optional[str] = Query(None,regex="\d{10}"), #Unique person ID
    queryname: Optional[str] = Query(None,min_length=1,max_length=30),
    querygender: Optional[str] = Query(None,regex="^[M|F]$"),
    queryage: Optional[str] = Query(None), #Young, Young Adult, Adult, Old Adult
    queryvisits: Optional[int] = Query(None),
    querylastvisit: Optional[datetime] = Query(None)):

    decoded_token=decodeJWT(authorization.replace("Bearer ",""))
    user_id=decoded_token["user_id"]

    resp= conn.execute("SELECT dbpersons.*, MAX(dbregister.created) AS 'lastvisit'"\
        " FROM dbregister INNER JOIN dbpersons ON dbregister.person_id = dbpersons.phone"\
        " AND dbregister.user_id='%s' GROUP BY dbpersons.phone ORDER BY lastvisit DESC LIMIT 100" %user_id).fetchall()


    if queryphone or queryname or querygender or queryage or queryvisits:
        resp=pd.DataFrame(resp, columns=["phone","name","gender","agerange","visits","lastvisit"])
        if queryphone or queryname:
            resp=resp[((resp["phone"] == queryphone) & (resp["phone"].notnull())) | ((resp["name"] == queryname) & (resp["name"].notnull()))]
        if querygender:
            resp=resp[(resp["gender"] == querygender) & (resp["gender"].notnull())]
        if queryage:
            resp=resp[(resp["agerange"] == queryage) & (resp["agerange"].notnull())]
        if queryvisits:
            resp=resp[(resp["visits"] == queryvisits) & (resp["visits"].notnull())]
        if querylastvisit:
            resp=resp[(resp["lastvisit"] == querylastvisit) & (resp["lastvisit"].notnull())]

        return resp.to_dict("records")
    else:
        return resp

@app.get('/messages')
async def get_messages(authorization: str = Header(...), ):
    decoded_token=decodeJWT(authorization.replace("Bearer ",""))
    user_id=decoded_token["user_id"]
    try:
        resp= conn.execute("SELECT * FROM dbmessages WHERE dbmessages.user_id = '%s'" %user_id).fetchall()
        return resp
    except:
        return {'message': 'La consulta salió mal'}


@app.post('/messages')
async def post_messages(authorization: str = Header(...), message: Message = Body(...) ):
    decoded_token=decodeJWT(authorization.replace("Bearer ",""))
    user_id=decoded_token["user_id"]
    
    resp=conn.execute(dbmessages.select().filter(dbmessages.c.id==message.message_id, dbmessages.c.user_id==user_id)).fetchall()
    
    if len(resp)>0:

        if len(message.text)>0:
            try:
                conn.execute(dbmessages.update().filter(dbmessages.c.id==message.message_id, dbmessages.c.user_id==user_id).values(text=message.text, label=message.label))
                return {'message':'Mensaje actualizado'}
            except:
                return {'message':'Error al escribir en la base de datos'}
        else:
            try:
                conn.execute(dbmessages.delete().where(dbmessages.c.id==message.message_id))
                return {'message':'Mensaje borrado'}
            except:
                return {'message':'Este mensaje está en uso. Intente borrar cuando se haya completado el envío'}
            
    
    else:
        if len(message.text)>0:
            to_dbmessages={
                "id":message.message_id,
                "text":message.text,
                "label":message.label,
                "user_id":user_id,
                }

            try:
                conn.execute(dbmessages.insert().values(to_dbmessages))
                return {'message':'Mensaje creado con éxito'}
            
            except:
                return {'message': 'La consulta salió mal'}
        else:
            return {'message':'No se puede crear un mensaje sin texto'}



@app.get("/analitics")
async def gen_analitics(authorization: str = Header(...), daysbefore: Optional[int] = Query(default=31)):
    decoded_token=decodeJWT(authorization.replace("Bearer ",""))
    user_id=decoded_token["user_id"]
    
    #query para obtener la hora:minuto promedio de visitas
    try:

        resp= conn.execute("SELECT * FROM ( "
        "SELECT dbpersons.phone, dbpersons.name, dbpersons.gender, dbpersons.agerange, dbpersons.visits, "\
        "dbregister.created, dbregister.service, dbregister.dispatched, dbregister.dispatchedat FROM "\
        "somosdb.dbpersons LEFT JOIN somosdb.dbregister ON dbregister.person_id=dbpersons.phone "\
        "WHERE dbregister.user_id = '%s' AND created >= NOW() - INTERVAL %d DAY ) AS table1" %(user_id,daysbefore)).fetchall()
        
        if resp:
            resp=pd.DataFrame(resp, columns=["phone","name","gender","agerange","visits","created","service","dispatched","dispatchedat"])
    
            genage=resp.groupby(['gender','agerange'])['agerange'].count()
            genage=genage.to_dict()
            

            topclients=resp[['phone',"name", 'visits', 'gender','agerange']].sort_values(by='visits', ascending=False)[:50]
            topclients=topclients.to_dict()
            

            mean_h=resp['created'].mean().hour
            if mean_h<10:
                mean_h='0'+str(mean_h)
            
            mean_h=str(mean_h)
            
            mean_m=resp['created'].mean().minute
            if mean_m<10:
                mean_m='0'+str(mean_m)
            mean_m=str(mean_m)

            meandispatched=str((resp['dispatchedat']-resp['created']).mean())

            servicecount=resp.groupby(['service'])['service'].count()
            servicecount=servicecount.to_dict()
            
            dispatchedcount=resp.groupby(['service','dispatched'])['dispatched'].count()
            dispatchedcount=dispatchedcount.to_dict()
            

            resp={'genage':genage, 'topclients':topclients, 
            'mean_h':mean_h, 'mean_m':mean_m, 'meandispatched':meandispatched,
            'servicecount':servicecount, 'dispatchedcount':dispatchedcount}

            resp['genage']=[k[0]+':'+k[1]+':'+str(v) for k,v in resp['genage'].items()]
            resp['servicecount']=[str(k)+ ':'+str(v) for k,v in resp['servicecount'].items()]
            resp['dispatchedcount']=[k[0]+':'+k[1]+':'+str(v) for k,v in resp['dispatchedcount'].items()]
            
            return resp
        else:
            return {'message': 'No hay datos que mostrar'}

    except:
        return {'message': 'La consulta salió mal'}
    
    

if __name__=='__main__':
    uvicorn.run(app, host='0.0.0.0', port=8000)