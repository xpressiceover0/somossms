#Pydantic
from pydantic import BaseModel, Field
from typing import Optional, List


#Modelos ----------------------------------------------
class LoginItem(BaseModel):
    username: str
    password: str

class TargetMassive(BaseModel): #modelo para enviar al massive
    phones: List[str] = Field(default=None) #Person.phone
    message_id: str = Field(default=None,max_length=36)
    toall: bool = Field(default=False)

#Modelo de mensaje
class Message(BaseModel):
   message_id: str = Field(...,max_length=36) #message ID
   text: Optional[str] = Field(default=None,min_lenght=0, max_length=160) 
   label: str = Field(..., min_length=1, max_length=15)

# Modelo de Usuario de la plataforma
class User(BaseModel):
    user_id: str = Field(...,max_length=36)
    name: str = Field(...,min_length=1,max_length=50)
    username: str = Field(..., min_length=5,max_length=20)
    password: str = Field(..., min_length=8, max_length=20)
    contact: str = Field(...,regex="\d{10}")
    location: str = Field(...,min_length=1,max_length=100)


#Modelo de Registro de visita
class Register(BaseModel):
    register_id: str = Field(...,max_length=36)
    phone: str = Field(...,regex="\d{10}") #Unique person ID
    name: str = Field(...,min_length=1,max_length=30)
    text: Optional[str] = Field(default=None)
    gender: str = Field(...,regex="^[M|F]$")
    agerange: str = Field(...) #Young, Young Adult, Adult, Old Adult
    visits: Optional[int] = Field(default=1) #no se recibe pues ya esta en la base
    service: str  = Field(...)
    dispatched: str = Field(...) #[-1 canceled] [0 waiting] [1 dispatched]