from fastapi import FastAPI

from app.api import chat, documents, auth
from app.core.config import APP_NAME
from app.core.logging_config import setup_logging
from app.db.database import init_db
from app.services.document_service import recover_pending_rebuilds

setup_logging()

app = FastAPI(title=APP_NAME)
from app.core.request_limits import UploadLimitMiddleware
app.add_middleware(UploadLimitMiddleware)

init_db()
recover_pending_rebuilds()

app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(chat.router)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": APP_NAME}