"""Recoverable document rebuilds, with an explicit cross-store recovery journal.

Readers in this process share INDEX_LOCK. This is not a distributed transaction:
run one API worker; external Chroma readers can observe the brief switch window.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
from uuid import uuid4

from app.core.config import CHUNK_OVERLAP, CHUNK_SIZE, METADATA_DB_PATH
from app.db.document_repository import delete_document, get_document, update_document
from app.services.chunker import chunk_document
from app.services.document_parser import parse_document_pages
from app.services.vector_store import VectorStore

INDEX_LOCK = threading.RLock()
_MAINTENANCE_LOCK = threading.Lock()
INDEX_BACKUP_DIR = METADATA_DB_PATH.parent / 'index_backups'


@contextmanager
def _maintenance_lock():
    """Serialize mutations; OS releases the advisory file lock on process exit."""
    if not _MAINTENANCE_LOCK.acquire(blocking=False):
        raise RuntimeError('Index maintenance is already running; retry later.')
    handle = None
    locked = False
    try:
        INDEX_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        handle = (INDEX_BACKUP_DIR / 'maintenance.lock').open('a+b')
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        locked = True
        yield
    finally:
        if handle is not None:
            if locked:
                handle.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
        _MAINTENANCE_LOCK.release()


def _write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    if os.name != 'nt':
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def _backup_document(document: dict, snapshot: dict) -> tuple[Path, dict]:
    key = hashlib.sha256(document['document_id'].encode()).hexdigest()[:12]
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    directory = INDEX_BACKUP_DIR / f'{key}_{stamp}_{uuid4().hex[:8]}'
    directory.mkdir(parents=True)
    source = Path(document['file_path'])
    original = directory / f'original{source.suffix.lower()}'
    shutil.copy2(source, original)
    with original.open('r+b') as stream:
        os.fsync(stream.fileno())
    _write_json(directory / 'document.json', document)
    _write_json(directory / 'vectors.json', snapshot)
    journal = {'version': 1, 'document_id': document['document_id'], 'state': 'backed_up',
               'new_ids': [], 'original_file': original.name}
    _write_json(directory / 'journal.json', journal)
    return directory, journal


def _rollback(directory: Path, journal: dict, store: VectorStore) -> None:
    snapshot = _read_json(directory / 'vectors.json')
    document = _read_json(directory / 'document.json')
    store.restore_document_snapshot(snapshot)
    old_ids = set(snapshot['ids'])
    store.delete_chunk_ids([value for value in journal['new_ids'] if value not in old_ids])
    restored = store.snapshot_document(journal['document_id'])
    if set(restored['ids']) != old_ids:
        raise RuntimeError('Index rollback verification failed; recovery journal retained.')
    update_document(journal['document_id'], {key: value for key, value in document.items() if key not in {'document_id', 'owner_id', 'visibility'}})
    journal['state'] = 'rolled_back'
    _write_json(directory / 'journal.json', journal)


def _recover_pending_locked(document_id: str | None = None) -> int:
    recovered = 0
    for path in sorted(INDEX_BACKUP_DIR.glob('*/journal.json')):
        journal = _read_json(path)
        if document_id is not None and journal['document_id'] != document_id:
            continue
        if journal['state'] == 'switching':
            # Any exception deliberately propagates: startup must fail closed.
            _rollback(path.parent, journal, VectorStore())
            recovered += 1
        elif journal['state'] == 'backed_up':
            # Embeddings were prepared without mutating either live database.
            journal['state'] = 'rolled_back'
            _write_json(path, journal)
            recovered += 1
    return recovered


def recover_pending_rebuilds() -> int:
    """Call at startup before accepting requests; failed recovery raises."""
    with _maintenance_lock(), INDEX_LOCK:
        return _recover_pending_locked()


def delete_document_by_id(document_id: str) -> dict:
    with _maintenance_lock(), INDEX_LOCK:
        _recover_pending_locked(document_id)
        document = get_document(document_id)
        if document is None:
            return {'success': False, 'message': 'Document not found.'}
        store = VectorStore()
        store.delete_by_document_id(document_id)
        from app.services.entity_aliases import delete_document_aliases
        delete_document_aliases(document_id)
        delete_document(document_id)
        file_path = Path(document['file_path'])
        if file_path.exists():
            file_path.unlink()
        return {'success': True, 'message': 'Document deleted successfully.'}


def _switch_document(document_id: str, store: VectorStore, prepared: dict,
                     snapshot: dict, directory: Path, journal: dict) -> int:
    """Caller holds INDEX_LOCK through success or complete rollback."""
    try:
        journal.update(state='switching', new_ids=prepared['ids'])
        _write_json(directory / 'journal.json', journal)
        chunk_count = store.add_prepared(prepared)
        staged_ids = set(store.snapshot_document(document_id)['ids'])
        if not set(prepared['ids']).issubset(staged_ids):
            raise RuntimeError('New index verification failed before deleting old chunks.')
        store.delete_chunk_ids(snapshot['ids'])
        actual_ids = store.snapshot_document(document_id)['ids']
        if len(actual_ids) != chunk_count or set(actual_ids) != set(prepared['ids']):
            raise RuntimeError('New index count verification failed.')
        update_document(document_id, {'status': 'indexed', 'chunk_count': chunk_count,
                        'vector_status': 'indexed', 'error_message': None})
        journal['state'] = 'committed'
        _write_json(directory / 'journal.json', journal)
        return chunk_count
    except Exception:
        # Do not release the reader lock between an unsuccessful switch and rollback.
        journal['state'] = 'switching'
        _write_json(directory / 'journal.json', journal)
        _rollback(directory, journal, store)
        raise


def rebuild_document_by_id(document_id: str) -> dict:
    with _maintenance_lock():
        with INDEX_LOCK:
            _recover_pending_locked(document_id)
            document = get_document(document_id)
            if document is None:
                return {'success': False, 'message': 'Document not found.'}
            file_path = Path(document['file_path'])
            if not file_path.exists():
                return {'success': False, 'message': 'Original file not found.'}
            store = VectorStore()
            snapshot = store.snapshot_document(document_id)
            directory, journal = _backup_document(document, snapshot)
        try:
            # Parse the preserved bytes so a concurrent external file edit cannot
            # change the input halfway through this rebuild.
            pages = parse_document_pages(directory / journal['original_file'])
            chunks = chunk_document(pages, source_file=document['filename'],
                                    chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP)
            if not chunks:
                raise ValueError('Document contains no extractable text; previous index retained.')
            # API calls are outside INDEX_LOCK: the old index stays searchable.
            prepared = store.prepare_chunks(chunks, document_id=document_id)
            with INDEX_LOCK:
                chunk_count = _switch_document(document_id, store, prepared, snapshot, directory, journal)
            return {'success': True, 'message': 'Document rebuilt successfully.',
                    'chunk_count': chunk_count, 'backup_path': str(directory)}
        except Exception as exc:
            if journal['state'] == 'switching':
                # A rollback failed. Keep the pending marker and fail closed.
                raise
            if journal['state'] == 'backed_up':
                journal['state'] = 'rolled_back'
                _write_json(directory / 'journal.json', journal)
            return {'success': False, 'message': str(exc), 'backup_path': str(directory)}
