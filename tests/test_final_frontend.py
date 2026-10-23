from pathlib import Path
from streamlit.testing.v1 import AppTest
from frontend.api_client import ApiClient


def test_logged_out_page_has_no_private_controls():
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1] / "frontend/streamlit_app.py")).run(timeout=15)
    assert not app.exception
    assert '登录' in [b.label for b in app.button]
    assert not app.file_uploader if hasattr(app,'file_uploader') else True
    assert '提交问题' not in [b.label for b in app.button]


def test_api_client_attaches_token_and_handles_401():
    calls=[]; cleared=[]
    class Response:
        status_code=401
        def json(self): return {'detail':'Please log in again.'}
    def get(url,**kwargs):
        calls.append(kwargs)
        return Response()
    client=ApiClient(get=get,token='test-token',on_unauthorized=lambda:cleared.append(True))
    from frontend.api_client import ApiClientError
    import pytest
    with pytest.raises(ApiClientError): client.list_documents()
    assert calls[0]['headers']['Authorization']=='Bearer test-token'
    assert cleared==[True]
