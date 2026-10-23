"""Argon2id passwords, signed short-lived JWTs and revocable SQLite sessions."""
import hashlib
import os
import secrets
import sqlite3
import time
from contextlib import closing
from threading import RLock

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.db import database

ACCESS_LOCK = RLock()
_hasher = PasswordHasher()
_dummy_hash = _hasher.hash(secrets.token_urlsafe(32))
_bearer = HTTPBearer(auto_error=False)


def secret_key():
    key = os.getenv('JWT_SECRET_KEY', '')
    if len(key) < 43 or key.lower().startswith(('your', 'change', 'replace')):
        raise RuntimeError('Configure JWT_SECRET_KEY with at least 32 random bytes (URL-safe encoded).')
    if os.getenv('JWT_ALGORITHM', 'HS256') != 'HS256':
        raise RuntimeError('Only HS256 is supported.')
    return key


def migrate(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','user')),
        is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0,1)),
        created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS auth_sessions (
        jti TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
        expires_at INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS login_attempts (
        bucket TEXT PRIMARY KEY, failures INTEGER NOT NULL, window_start INTEGER NOT NULL)''')
    for table, definitions in {
        'documents': {'owner_id': 'INTEGER REFERENCES users(id)', 'visibility': "TEXT NOT NULL DEFAULT 'private' CHECK(visibility IN ('private','shared'))"},
        'chat_history': {'user_id': 'INTEGER REFERENCES users(id)', 'document_ids_json': 'TEXT'},
    }.items():
        columns = {row[1] for row in conn.execute('PRAGMA table_info('+table+')')}
        for name, kind in definitions.items():
            if name not in columns:
                conn.execute('ALTER TABLE '+table+' ADD COLUMN '+name+' '+kind)
    conn.execute('CREATE INDEX IF NOT EXISTS idx_sessions_user ON auth_sessions(user_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_history_user ON chat_history(user_id,id)')


def public_user(row):
    return {key: row[key] for key in ('id','username','role','is_active','created_at','updated_at')}


def create_user(username, password, role='user', *, bootstrap=False):
    if not username or len(username)>64 or username != username.strip():
        raise HTTPException(422, 'Invalid username.')
    if not 12 <= len(password) <= 256:
        raise HTTPException(422, 'Password must contain 12–256 characters.')
    if role not in {'admin','user'}:
        raise HTTPException(422, 'Invalid role.')
    hashed = _hasher.hash(password)
    now = int(time.time())
    with ACCESS_LOCK, closing(database.get_connection()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        if bootstrap and conn.execute('SELECT 1 FROM users').fetchone():
            raise HTTPException(409, 'Bootstrap is only allowed before any account exists.')
        try:
            cursor = conn.execute('INSERT INTO users(username,password_hash,role,created_at,updated_at) VALUES(?,?,?,?,?)',
                                  (username,hashed,role,now,now))
        except sqlite3.IntegrityError:
            raise HTTPException(409,'Username already exists.') from None
        uid = cursor.lastrowid
        if bootstrap:
            if role != 'admin':
                raise HTTPException(422,'Initial account must be admin.')
            conn.execute("UPDATE documents SET owner_id=?, visibility='private' WHERE owner_id IS NULL",(uid,))
            conn.execute('UPDATE chat_history SET user_id=? WHERE user_id IS NULL',(uid,))
        row = conn.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
        return public_user(row)


def login(username, password, address):
    key = secret_key()
    now = int(time.time())
    buckets = [('user',username,5),('ip',address,30)]
    buckets = [(hashlib.sha256((kind+':'+value).encode()).hexdigest(),limit) for kind,value,limit in buckets]
    with ACCESS_LOCK, closing(database.get_connection()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('DELETE FROM login_attempts WHERE window_start < ?',(now-900,))
        conn.execute('DELETE FROM auth_sessions WHERE expires_at < ?',(now,))
        for bucket,limit in buckets:
            row=conn.execute('SELECT failures FROM login_attempts WHERE bucket=?',(bucket,)).fetchone()
            if row and row['failures']>=limit:
                raise HTTPException(429,'Too many login attempts. Retry later.',headers={'Retry-After':'900'})
        row=conn.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
        try:
            valid=_hasher.verify(row['password_hash'] if row else _dummy_hash,password)
        except (VerificationError,InvalidHashError):
            valid=False
        if not row or not valid or not row['is_active']:
            for bucket,limit in buckets:
                conn.execute('INSERT INTO login_attempts VALUES(?,1,?) ON CONFLICT(bucket) DO UPDATE SET failures=failures+1',(bucket,now))
            conn.commit()  # Failure counters must survive the HTTP exception.
            raise HTTPException(401,'Invalid username or password.')
        conn.execute('DELETE FROM login_attempts WHERE bucket=?',(buckets[0][0],))
        if _hasher.check_needs_rehash(row['password_hash']):
            conn.execute('UPDATE users SET password_hash=? WHERE id=?',(_hasher.hash(password),row['id']))
        minutes=int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES','60'))
        if not 1<=minutes<=1440:
            raise RuntimeError('ACCESS_TOKEN_EXPIRE_MINUTES must be 1–1440.')
        expires=now+minutes*60
        jti=secrets.token_urlsafe(32)
        conn.execute('INSERT INTO auth_sessions(jti,user_id,expires_at) VALUES(?,?,?)',(jti,row['id'],expires))
        token=jwt.encode({'sub':str(row['id']),'jti':jti,'iat':now,'exp':expires,'iss':'rag-knowledge-base','aud':'rag-api'},key,algorithm='HS256')
        return {'access_token':token,'token_type':'bearer','expires_in':minutes*60,'user':public_user(row)}


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)):
    failure=HTTPException(401,'Please log in again.',headers={'WWW-Authenticate':'Bearer'})
    if credentials is None:
        raise failure
    try:
        claims=jwt.decode(credentials.credentials,secret_key(),algorithms=['HS256'],audience='rag-api',issuer='rag-knowledge-base',
                          options={'require':['sub','jti','iat','exp']})
        uid=int(claims['sub'])
    except (jwt.InvalidTokenError,ValueError,TypeError,KeyError):
        raise failure from None
    with closing(database.get_connection()) as conn:
        row=conn.execute('''SELECT u.* FROM users u JOIN auth_sessions s ON s.user_id=u.id
            WHERE u.id=? AND s.jti=? AND s.revoked=0 AND s.expires_at>? AND u.is_active=1''',
            (uid,claims['jti'],int(time.time()))).fetchone()
    if row is None:
        raise failure
    return {**public_user(row),'session_jti':claims['jti']}


def admin_user(user=Depends(current_user)):
    if user['role']!='admin':
        raise HTTPException(403,'Administrator access required.')
    return user


def update_user(uid, updates):
    with ACCESS_LOCK, closing(database.get_connection()) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        row=conn.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
        if row is None:
            raise HTTPException(404,'User not found.')
        active=updates.get('is_active',bool(row['is_active']))
        role=updates.get('role',row['role'])
        if row['role']=='admin' and row['is_active'] and (not active or role!='admin'):
            count=conn.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=1").fetchone()[0]
            if count<=1:
                raise HTTPException(409,'Cannot disable or demote the last active administrator.')
        conn.execute('UPDATE users SET role=?,is_active=?,updated_at=? WHERE id=?',(role,int(active),int(time.time()),uid))
        conn.execute('UPDATE auth_sessions SET revoked=1 WHERE user_id=?',(uid,))
        return public_user(conn.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone())


def reset_password(uid,password):
    hashed=_hasher.hash(password)
    with ACCESS_LOCK, closing(database.get_connection()) as conn, conn:
        cursor=conn.execute('UPDATE users SET password_hash=?,updated_at=? WHERE id=?',(hashed,int(time.time()),uid))
        if not cursor.rowcount:
            raise HTTPException(404,'User not found.')
        conn.execute('UPDATE auth_sessions SET revoked=1 WHERE user_id=?',(uid,))



def refresh_identity(user):
    """Revalidate after acquiring the operation lock; queued identities may be stale."""
    with closing(database.get_connection()) as conn:
        row = conn.execute('''SELECT u.* FROM users u JOIN auth_sessions s ON s.user_id=u.id
            WHERE u.id=? AND s.jti=? AND s.revoked=0 AND s.expires_at>? AND u.is_active=1''',
            (user['id'], user.get('session_jti'), int(time.time()))).fetchone()
    if row is None:
        raise HTTPException(401, 'Please log in again.')
    return {**public_user(row), 'session_jti': user['session_jti']}


def locked_access(function):
    """Single-worker authorization linearization with revocation/visibility writes."""
    from functools import wraps
    from inspect import signature
    sig = signature(function)
    @wraps(function)
    def guarded(*args, **kwargs):
        with ACCESS_LOCK:
            bound = sig.bind(*args, **kwargs)
            for name in ('user', 'admin'):
                if name in bound.arguments:
                    fresh = refresh_identity(bound.arguments[name])
                    default = sig.parameters[name].default
                    if getattr(default, 'dependency', None) is admin_user and fresh['role'] != 'admin':
                        raise HTTPException(403, 'Administrator access required.')
                    bound.arguments[name] = fresh
            return function(*bound.args, **bound.kwargs)
    return guarded
