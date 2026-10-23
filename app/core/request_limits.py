"""Bound upload bytes before multipart spooling, including chunked requests."""
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.responses import JSONResponse
from app.services.auth_service import current_user

MAX_REQUEST_BYTES = 21 * 1024 * 1024  # 20 MiB file plus bounded multipart overhead.

class UploadLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('path','').rstrip('/') != '/documents/upload':
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        raw = headers.get(b'authorization', b'').decode('latin1')
        scheme, _, token = raw.partition(' ')
        try:
            credentials = HTTPAuthorizationCredentials(scheme=scheme, credentials=token) if scheme.lower() == 'bearer' and token else None
            current_user(credentials)
        except HTTPException as exc:
            return await JSONResponse({'detail': exc.detail}, status_code=exc.status_code)(scope, receive, send)
        length = headers.get(b'content-length')
        if length is not None:
            try:
                oversized = int(length) > MAX_REQUEST_BYTES or int(length) < 0
            except ValueError:
                oversized = True
            if oversized:
                return await JSONResponse({'detail':'Upload request too large.'}, status_code=413)(scope, receive, send)
        total = 0
        async def limited_receive():
            nonlocal total
            message = await receive()
            if message['type'] == 'http.request':
                total += len(message.get('body', b''))
                if total > MAX_REQUEST_BYTES:
                    raise HTTPException(413, 'Upload request too large.')
            return message
        await self.app(scope, limited_receive, send)
