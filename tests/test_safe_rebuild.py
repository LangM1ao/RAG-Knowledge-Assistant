import json
from pathlib import Path

import pytest

from app.db import document_repository as repository
from app.services import document_service, vector_store
from app.services.chunker import TextChunk


@pytest.fixture
def indexed_document(tmp_path, monkeypatch):
    monkeypatch.setattr(repository, 'METADATA_DB_PATH', tmp_path / 'metadata.db')
    monkeypatch.setattr(document_service, 'INDEX_BACKUP_DIR', tmp_path / 'index_backups', raising=False)
    monkeypatch.setattr(document_service, 'CHUNK_SIZE', 40, raising=False)
    monkeypatch.setattr(document_service, 'CHUNK_OVERLAP', 5, raising=False)
    monkeypatch.setattr(vector_store, 'embed_text', lambda text: [1.0, 0.0, 0.0])
    path = tmp_path / 'source.txt'
    path.write_text('# New section\n' + 'New content. ' * 12, encoding='utf-8')
    document = {'document_id': 'doc-1', 'filename': path.name, 'file_path': str(path),
                'file_type': '.txt', 'upload_time': '2026-10-22T00:00:00',
                'status': 'indexed', 'chunk_count': 1, 'vector_status': 'indexed', 'error_message': None}
    repository.create_document(document)
    store = vector_store.VectorStore(db_path=tmp_path / 'chroma')
    store.add_chunks([TextChunk('old', 'Original indexed text.', path.name, 0, 22)], document_id='doc-1')
    monkeypatch.setattr(document_service, 'VectorStore', lambda: store)
    return store, document, tmp_path


def stored_rows(store):
    result = store.collection.get(where={'document_id': 'doc-1'}, include=['documents', 'metadatas', 'embeddings'])
    return {chunk_id: (text, metadata, list(embedding)) for chunk_id, text, metadata, embedding in zip(
        result['ids'], result['documents'], result['metadatas'], result['embeddings'])}


def test_rebuild_backs_up_original_record_file_and_embeddings_before_replacement(indexed_document):
    store, document, directory = indexed_document
    result = document_service.rebuild_document_by_id('doc-1')
    assert result['success'] is True
    rows = stored_rows(store)
    assert 'old' not in rows
    assert len(rows) == repository.get_document('doc-1')['chunk_count'] > 1
    assert all(len(row[0]) <= 40 and row[1]['section_title'] == 'New section' for row in rows.values())
    journals = list((directory / 'index_backups').glob('*/journal.json'))
    assert len(journals) == 1
    assert json.loads(journals[0].read_text())['state'] == 'committed'
    backup = journals[0].parent
    assert json.loads((backup / 'document.json').read_text()) == document
    snapshot = json.loads((backup / 'vectors.json').read_text())
    assert snapshot['ids'] == ['old']
    assert snapshot['embeddings'] == [[1.0, 0.0, 0.0]]
    assert (backup / 'original.txt').read_bytes() == Path(document['file_path']).read_bytes()


def test_failed_embedding_keeps_old_searchable_index_and_record(indexed_document, monkeypatch):
    store, document, _ = indexed_document
    old_rows = stored_rows(store)
    def fail_embedding(text):
        raise RuntimeError('embedding unavailable')
    monkeypatch.setattr(vector_store, 'embed_text', fail_embedding)
    result = document_service.rebuild_document_by_id('doc-1')
    assert result['success'] is False
    assert stored_rows(store) == old_rows
    assert repository.get_document('doc-1') == document


def test_partial_index_write_rolls_back_new_chunks_without_losing_old_embeddings(indexed_document, monkeypatch):
    store, document, _ = indexed_document
    old_rows = stored_rows(store)
    add = store.add_prepared
    def fail_after_write(prepared):
        add(prepared)
        raise RuntimeError('write failed after insertion')
    monkeypatch.setattr(store, 'add_prepared', fail_after_write)
    result = document_service.rebuild_document_by_id('doc-1')
    assert result['success'] is False
    assert stored_rows(store) == old_rows
    assert repository.get_document('doc-1') == document


def test_record_update_failure_restores_old_index_and_record(indexed_document, monkeypatch):
    store, document, _ = indexed_document
    old_rows = stored_rows(store)
    update = document_service.update_document
    def fail_new_record(document_id, fields):
        if fields.get('chunk_count', 0) > 1:
            raise RuntimeError('metadata commit failed')
        return update(document_id, fields)
    monkeypatch.setattr(document_service, 'update_document', fail_new_record)
    result = document_service.rebuild_document_by_id('doc-1')
    assert result['success'] is False
    assert stored_rows(store) == old_rows
    assert repository.get_document('doc-1') == document


def test_interrupted_switch_is_recovered_from_durable_journal(indexed_document, monkeypatch):
    store, document, directory = indexed_document
    old_rows = stored_rows(store)
    add = store.add_prepared
    def interrupt_after_write(prepared):
        add(prepared)
        raise KeyboardInterrupt('simulated process interruption')
    monkeypatch.setattr(store, 'add_prepared', interrupt_after_write)
    with pytest.raises(KeyboardInterrupt):
        document_service.rebuild_document_by_id('doc-1')
    assert len(stored_rows(store)) > 1
    assert document_service.recover_pending_rebuilds() == 1
    assert stored_rows(store) == old_rows
    assert repository.get_document('doc-1') == document
    journal = next((directory / 'index_backups').glob('*/journal.json'))
    assert json.loads(journal.read_text())['state'] == 'rolled_back'


def test_repeated_rebuild_does_not_duplicate_chunks(indexed_document):
    store, _, _ = indexed_document
    first = document_service.rebuild_document_by_id('doc-1')
    second = document_service.rebuild_document_by_id('doc-1')
    assert first['success'] and second['success']
    assert len(stored_rows(store)) == first['chunk_count'] == second['chunk_count']


def test_empty_replacement_keeps_the_previous_searchable_document(indexed_document):
    store, document, _ = indexed_document
    old_rows = stored_rows(store)
    Path(document['file_path']).write_text(' \n\t', encoding='utf-8')
    result = document_service.rebuild_document_by_id('doc-1')
    assert result['success'] is False
    assert stored_rows(store) == old_rows
    assert repository.get_document('doc-1') == document


def test_recovery_failure_propagates_and_keeps_pending_journal(indexed_document, monkeypatch):
    store, _, directory = indexed_document
    add = store.add_prepared
    def interrupt_after_write(prepared):
        add(prepared)
        raise KeyboardInterrupt()
    monkeypatch.setattr(store, 'add_prepared', interrupt_after_write)
    with pytest.raises(KeyboardInterrupt):
        document_service.rebuild_document_by_id('doc-1')
    def fail_restore(snapshot):
        raise RuntimeError('restore storage unavailable')
    monkeypatch.setattr(store, 'restore_document_snapshot', fail_restore)
    with pytest.raises(RuntimeError, match='restore storage unavailable'):
        document_service.recover_pending_rebuilds()
    journal = next((directory / 'index_backups').glob('*/journal.json'))
    assert json.loads(journal.read_text())['state'] == 'switching'


def test_preparing_embeddings_allows_reads_but_blocks_competing_maintenance(indexed_document, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    store, _, _ = indexed_document
    preparing = threading.Event()
    proceed = threading.Event()
    def slow_embedding(text):
        preparing.set()
        assert proceed.wait(timeout=5)
        return [1.0, 0.0, 0.0]
    monkeypatch.setattr(vector_store, 'embed_text', slow_embedding)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(document_service.rebuild_document_by_id, 'doc-1')
        assert preparing.wait(timeout=5)
        try:
            assert document_service.INDEX_LOCK.acquire(timeout=1)
            try:
                assert set(stored_rows(store)) == {'old'}
            finally:
                document_service.INDEX_LOCK.release()
            with pytest.raises(RuntimeError, match='maintenance'):
                document_service.rebuild_document_by_id('doc-1')
        finally:
            proceed.set()
        assert future.result(timeout=5)['success']


def test_new_chunk_count_mismatch_rolls_back_even_without_storage_exception(indexed_document, monkeypatch):
    store, document, _ = indexed_document
    old_rows = stored_rows(store)
    add = store.add_prepared
    def incomplete_write(prepared):
        add({key: values[:1] for key, values in prepared.items()})
        return len(prepared['ids'])
    monkeypatch.setattr(store, 'add_prepared', incomplete_write)
    assert document_service.rebuild_document_by_id('doc-1')['success'] is False
    assert stored_rows(store) == old_rows
    assert repository.get_document('doc-1') == document


def test_initial_indexing_and_deletion_keep_upload_lifecycle_working(indexed_document):
    from app.services.entity_aliases import set_document_aliases
    store, document, _ = indexed_document
    store.delete_by_document_id('doc-1')
    repository.update_document('doc-1', {'status': 'parsed', 'chunk_count': 0, 'vector_status': 'not_indexed'})
    assert document_service.rebuild_document_by_id('doc-1')['success']
    set_document_aliases('doc-1', 'Example Person', ['Example'])
    assert document_service.delete_document_by_id('doc-1')['success']
    assert repository.get_document('doc-1') is None
    assert stored_rows(store) == {}
    assert not Path(document['file_path']).exists()
    with repository.get_connection() as connection:
        assert connection.execute('SELECT COUNT(*) FROM entity_aliases WHERE document_id=?', ('doc-1',)).fetchone()[0] == 0


def test_persisted_pdf_metadata_and_offsets_survive_snapshot(tmp_path, monkeypatch):
    from app.services.chunker import chunk_document
    from app.services.document_parser import DocumentPage
    monkeypatch.setattr(vector_store, 'embed_text', lambda text: [1.0, 0.0, 0.0])
    store = vector_store.VectorStore(db_path=tmp_path / 'pdf_chroma')
    pages = [DocumentPage('PROFILE\nA person.', 1), DocumentPage('EDUCATION\nA degree.', 2)]
    chunks = chunk_document(pages, 'resume.pdf', 100, 10)
    store.add_chunks(chunks, 'pdf-1')
    rows = store.snapshot_document('pdf-1')
    metadata = sorted(rows['metadatas'], key=lambda item: item['chunk_index'])
    assert metadata[1]['page_number'] == 2
    assert json.loads(metadata[1]['page_range']) == [2, 2]
    assert metadata[1]['page_start'] == metadata[1]['page_end'] == 2
    assert metadata[1]['section_title'] == 'EDUCATION'
    assert metadata[1]['start_index'] == 18
