from sqlalchemy import Table, Column, ForeignKey
from sqlalchemy.sql.sqltypes import Integer,String,DateTime,SmallInteger,CHAR
from config.db import meta, engine

# USUARIOS CLIENTES DE SOMOS =============================================================================================
#Los usuarios pueden ser creados y no dependen de ninguna tabla para existir ya que puede haber usuarios sin ningun tipo de interaccion
dbusers=Table("dbusers",meta,
    Column("id", String(36), primary_key=True), # validación y agragacion de tablas dependientes
    Column("created", DateTime), # informacion
    Column("name", String(50), unique=True), # informacion y uso en mensajes y promociones como dato payload
    Column("username", String(20), unique=True), # login y registro
    Column("password", String(150)), # login y registro
    Column("contact", String(10)), # informacion
    Column("location", String(100)), # informacion
    Column("leftpromo", Integer), # mensajes promocionales restantes
    Column("isactive", SmallInteger)) # validacion de uso de la plataforma


# DATOS DE PERSONAS Y TELEFONO ========================================================================================
#Las personas son clientes que consumen con nuestros usuarios, una persona es añadida y actualizada mediante los registros
dbpersons=Table("dbpersons",meta,
    Column("phone", String(10), primary_key=True), #La persona debe tener un único telefono al que llegaran sus notificaciones. No hay mas de una persona con el mismo telefono
    Column("name", String(30)), # # informacion y uso en mensajes y promociones como dato payload
    Column("gender", CHAR), # informacion y agregacion de mercado
    Column("agerange", String(12)), # informacion y agregacion de mercado
    Column("visits", Integer)) # informacion y agregacion de mercado. Visitas generales de todos nuestros usuarios


# REGISTER ===========================================================================================================
# el registro es la actividad general y principal de todos nuestros usuarios y es la que desencadena una peticion de SMS
# un registro ocurre cuando una persona acude al usuario en busca de un servicio, es independientemente de si es atendido de inmediato o no
# tiene la finalidad de obtener los datos de una persona y del usuario que presta su servicio
# el registro tiene un estado que es modificado dependiendo del tipo de situacion que se presentó ante el registro
# las situaciones varían en los siguientes estados:
# [1] la persona fue atendida de inmediato y no requirió usar la infraestructura de SMS
# [0] la persona entró en lista de espera y se encuentra esperando a que se desocupe un lugar y se le notifique por SMS
# [2] la persona entró en lista y al recibir su notificacion SMS confirmó con OK
# [3] la persona entró en lista y al recibir su notificacion SMS no respondió pero se presentó antes del tiempo de espera y fue despachado
# [-1] la persona entro en lista y al recibir su notificacion SMS canceló con CANCELAR
# [-2] la persona entro en lista y al recibir su notificacion SMS no respondió y acabo el tiempo de espera por lo que se canceló
dbregister=Table("dbregister",meta,
    Column("id", String(36), primary_key=True),# identificador unico del registro
    Column("created", DateTime), # fecha en que la perona solicito servicio al usuario
    Column("person_id",String(10), ForeignKey("dbpersons.phone")), # telefono de la persona que fue registrada
    Column("user_id",String(36), ForeignKey("dbusers.id")), # identificador del usuario para saber con cual usuario se solicitó el registro
    Column("service", String(20)), # Texto o ID de servicio que ofrezca el usuario
    Column("dispatched", String(15)), # situacion en la que el usuario quedó al hacer su peticion
    Column("dispatchedat",DateTime)) # tiempo en que la petición de la persona registrada fue procesada haya sido cancelada o no
    
    # dispatched = 1 es que la persona no necesitó esperar de otra forma, hay 4 modos y todos implican sms: 
    # dispatched = 0 peticion de SMS en pool
    # dispatched = 2 confirmó acceso con respuesta OK y llegó en tiempo razonable
    # dispatched = 3 no confirmó acceso con SMS pero llegó antes del timeout
    # dispatched = -1 cancelado por persona con respesta CANCELAR
    # dispatched = -2 cancelado por timeout,
    # dispatched = -3 confirmó acceso con respuesta OK y no llegó


# POOL ===============================================================================================================
# Pool es una tabla donde se almacenan las peticiones pendientes de SMS (que en el registro entraron con dispatched=0) 
# a la que se le va a hacer un request desde el script que tiene conexión con arduino por lo que debe contener necesariamente:
# [phone o person_id], [name], [msj], [msj_id], [user], [register_id], [user_id]
# el pool se actualiza desde el frontend cuando se pulsa el boton WAIT y esto hace que el registro entre con dispatched=0
# el script de peticiones pide la lista con elementos dispatched=0 para ponerlos en cola de mensaje
# si no ocurrio nungun error en el envío de sms, arduino devuelve el phone y OK y se asocia el phone al register_id
# usando el register_id del registro por el que fue enviado el sms se actualiza el pool al modo de espera de respuesta
dbpool=Table("dbpool",meta,
    Column("phone", String(10), primary_key=True),
    Column("text", String(160)),
    Column("register_id", String(36), ForeignKey("dbregister.id")),
    Column("done",String(8)))
    # done = None es que los datos estan en standby esperando a que el boton de NOTIFY sea pulsado
    # done = 0 es que el boton de NOTIFY fue pulsado y los datos estan listos para ser leidos por el script de arduino
    #________________________________________________________________________________________________________
    # donde = 1 es que los datos ya fueron leidos por el script de arduino y esta en espera de c onfirmar envio exitoso
    # dome = 2 es que el mensaje fue enviado y esta en espera de respuesta o de que caduque el tiempo de espera
    # done = -1 es que hubo error en el envio

dbmassive=Table("dbmassive",meta,
    Column("id", String(36), primary_key=True),# identificador unico del registro
    Column("phone", String(10),),
    Column("message_id", String(36), ForeignKey("dbmessages.id")),
    Column("user_id", String(36), ForeignKey("dbusers.id")),
    Column("done",String(8)))


dbmessages=Table("dbmessages",meta,
    Column("id",String(36), primary_key=True),
    Column("text", String(160)), #NULL si es mensaje de notificacion precargado, de lo contrario, se sacará el mensaje
    Column("label", String(15)),
    Column("user_id", String(36), ForeignKey("dbusers.id")))

meta.create_all(engine)