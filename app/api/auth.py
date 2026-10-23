from app.services.auth_service import locked_access
from contextlib import closing
from typing import Literal
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, ConfigDict
from app.db import database
from app.services import auth_service as auth

router=APIRouter(tags=['authentication'])
class Login(BaseModel):
    model_config=ConfigDict(extra='forbid')
    username:str=Field(min_length=1,max_length=64)
    password:str=Field(min_length=1,max_length=256,repr=False)
class NewUser(Login):
    password:str=Field(min_length=12,max_length=256,repr=False)
    role:Literal['admin','user']='user'
class UserUpdate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    role:Literal['admin','user']|None=None
    is_active:bool|None=None
class PasswordReset(BaseModel):
    model_config=ConfigDict(extra='forbid')
    password:str=Field(min_length=12,max_length=256,repr=False)

@router.post('/auth/login')
def login(body:Login,request:Request):
    return auth.login(body.username,body.password,request.client.host if request.client else 'local')

@router.get('/auth/me')
@locked_access
def me(user=Depends(auth.current_user)):
    return auth.public_user(user)

@router.post('/auth/logout')
@locked_access
def logout(user=Depends(auth.current_user)):
    with closing(database.get_connection()) as conn,conn:
        conn.execute('UPDATE auth_sessions SET revoked=1 WHERE jti=?',(user['session_jti'],))
    return {'success':True}

@router.get('/admin/users')
@locked_access
def users(admin=Depends(auth.admin_user)):
    with closing(database.get_connection()) as conn:
        return {'users':[auth.public_user(row) for row in conn.execute('SELECT * FROM users ORDER BY id')]}

@router.post('/admin/users',status_code=201)
@locked_access
def create(body:NewUser,admin=Depends(auth.admin_user)):
    return auth.create_user(body.username,body.password,body.role)

@router.patch('/admin/users/{user_id}')
@locked_access
def update(user_id:int,body:UserUpdate,admin=Depends(auth.admin_user)):
    return auth.update_user(user_id,body.model_dump(exclude_none=True))

@router.post('/admin/users/{user_id}/reset-password')
@locked_access
def reset(user_id:int,body:PasswordReset,admin=Depends(auth.admin_user)):
    auth.reset_password(user_id,body.password)
    return {'success':True}
