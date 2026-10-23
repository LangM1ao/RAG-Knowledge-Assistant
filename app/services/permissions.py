"""Document authorization uses verified identities and current SQLite records."""
from fastapi import HTTPException
from app.db.document_repository import get_document, list_document_records

def can_read_document(user,document):
    return user['role']=='admin' or document.get('owner_id')==user['id'] or document.get('visibility')=='shared'

def can_modify_document(user,document):
    return user['role']=='admin' or document.get('owner_id')==user['id']

def require_document(user,document_id,*,modify=False):
    document=get_document(document_id)
    check=can_modify_document if modify else can_read_document
    if document is None or not check(user,document):
        raise HTTPException(404,'Document not found.')
    return document

def accessible_documents(user):
    return [d for d in list_document_records() if can_read_document(user,d)]

def resolve_scope(user,selected_ids=None,source_files=None):
    documents=accessible_documents(user)
    allowed={d['document_id'] for d in documents}
    if selected_ids is not None:
        if not set(selected_ids)<=allowed:
            raise HTTPException(403,'Requested document scope is not accessible.')
        allowed &= set(selected_ids)
    if source_files is not None:
        allowed &= {d['document_id'] for d in documents if d['filename'] in source_files}
    return sorted(allowed)
