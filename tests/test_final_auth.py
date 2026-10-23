import secrets
import time
import jwt
import pytest
from fastapi.testclient import TestClient
from app.db import database, document_repository
from app.services import auth_service as auth

@pytest.fixture
def secured(tmp_path, monkeypatch):
    path = tmp_path / 'auth.db'
    monkeypatch.setattr(database, 'METADATA_DB_PATH', path)
    monkeypatch.setattr(document_repository, 'METADATA_DB_PATH', path)
    monkeypatch.setenv('JWT_SECRET_KEY', secrets.token_urlsafe(48))
    database.init_db()
    from app.main import app
    app.dependency_overrides.clear()
    admin = auth.create_user('admin', 'Test-password-admin-123!', 'admin', bootstrap=True)
    alice = auth.create_user('alice', 'Test-password-alice-123!', 'user')
    bob = auth.create_user('bob', 'Test-password-bob-123!', 'user')
    with TestClient(app) as client:
        yield client, {'admin': admin, 'alice': alice, 'bob': bob}
    app.dependency_overrides.clear()

def headers(client, name):
    response = client.post('/auth/login', json={'username': name, 'password': 'Test-password-'+name+'-123!'})
    assert response.status_code == 200, response.text
    return {'Authorization': 'Bearer '+response.json()['access_token']}

def test_login_logout_and_password_hash(secured):
    c, users = secured
    h = headers(c, 'alice')
    assert c.get('/auth/me', headers=h).json()['id'] == users['alice']['id']
    assert c.get('/documents/list').status_code == 401
    assert c.get('/auth/me', headers={'Authorization':'Bearer invalid'}).status_code == 401
    for name in ['alice', 'missing']:
        assert c.post('/auth/login',json={'username':name,'password':'wrong'}).status_code == 401
    with database.get_connection() as db:
        stored = db.execute('SELECT password_hash FROM users WHERE username=?',('alice',)).fetchone()[0]
    assert stored.startswith('$argon2id$') and 'Test-password' not in stored
    assert c.post('/auth/logout',headers=h).status_code == 200
    assert c.get('/auth/me',headers=h).status_code == 401

def test_admin_disable_reset_and_last_admin(secured):
    c,u=secured
    ah=headers(c,'admin'); bh=headers(c,'bob')
    assert c.get('/admin/users',headers=bh).status_code == 403
    assert c.post('/admin/users',headers=ah,json={'username':'alice','password':'Another-long-password!','role':'user'}).status_code == 409
    assert c.patch('/admin/users/'+str(u['admin']['id']),headers=ah,json={'is_active':False}).status_code == 409
    assert c.patch('/admin/users/'+str(u['bob']['id']),headers=ah,json={'is_active':False}).status_code == 200
    assert c.get('/auth/me',headers=bh).status_code == 401
    h=headers(c,'alice')
    assert c.post('/admin/users/'+str(u['alice']['id'])+'/reset-password',headers=ah,json={'password':'Changed-password-123!'}).status_code == 200
    assert c.get('/auth/me',headers=h).status_code == 401

def test_expiry_signature_and_throttle(secured,monkeypatch):
    import os
    c,u=secured; h=headers(c,'alice')
    token=h['Authorization'].split()[1]
    claims=jwt.decode(token,os.environ['JWT_SECRET_KEY'],algorithms=['HS256'],audience='rag-api')
    claims['exp']=int(time.time())-10
    expired=jwt.encode(claims,os.environ['JWT_SECRET_KEY'],algorithm='HS256')
    assert c.get('/auth/me',headers={'Authorization':'Bearer '+expired}).status_code == 401
    forged=jwt.encode({**claims,'exp':int(time.time())+100},secrets.token_urlsafe(48),algorithm='HS256')
    assert c.get('/auth/me',headers={'Authorization':'Bearer '+forged}).status_code == 401
    results=[c.post('/auth/login',json={'username':'missing','password':'wrong'}).status_code for _ in range(12)]
    assert 429 in results


def test_queued_identity_is_revalidated_after_revocation(secured):
    from app.services.auth_service import current_user
    from fastapi.security import HTTPAuthorizationCredentials
    from fastapi import HTTPException
    from app.api.chat import query_knowledge_base
    from app.schemas.chat import ChatQueryRequest
    c,u=secured
    h=headers(c,'admin')
    token=h['Authorization'].split()[1]
    stale=current_user(HTTPAuthorizationCredentials(scheme='Bearer',credentials=token))
    assert c.post('/auth/logout',headers=h).status_code==200
    with pytest.raises(HTTPException) as error:
        query_knowledge_base(ChatQueryRequest(question='private'),user=stale)
    assert error.value.status_code==401
