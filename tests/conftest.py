"""Regression API unit tests inject identity explicitly; security tests use real JWT login."""
import os
import tempfile
from pathlib import Path
import pytest

# Never initialize or migrate business databases while collecting tests.
_TEST_ROOT=Path(tempfile.mkdtemp(prefix='rag-suite-'))
os.environ['METADATA_DB_PATH']=str(_TEST_ROOT/'metadata.db')
os.environ['CHROMA_DB_DIR']=str(_TEST_ROOT/'chroma')
os.environ['UPLOAD_DIR']=str(_TEST_ROOT/'uploads')
os.environ['OPENAI_API_KEY']='test-key-no-network'

@pytest.fixture
def legacy_api_identity(monkeypatch):
    from app.main import app
    from app.services.auth_service import current_user
    from app.services import auth_service
    monkeypatch.setattr(auth_service, "refresh_identity", lambda user: user)
    from app.api import chat
    app.dependency_overrides[current_user]=lambda:{'id':1,'username':'fixture','role':'user','is_active':1}
    monkeypatch.setattr(chat,'resolve_scope',lambda user,selected_ids=None,source_files=None:selected_ids if selected_ids is not None else ['doc-1'])
    yield
    app.dependency_overrides.clear()
