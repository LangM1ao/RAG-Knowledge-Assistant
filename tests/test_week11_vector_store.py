from pathlib import Path

import pytest

from app.services import vector_store
from app.services.vector_store import VectorStore, build_where_filter


def test_build_where_filter_handles_none_single_multiple_and_combined():
    assert build_where_filter() is None
    assert build_where_filter(source_files=["policy.txt"]) == {
        "source_file": "policy.txt"
    }
    assert build_where_filter(source_files=["a.txt", "b.txt"]) == {
        "source_file": {"$in": ["a.txt", "b.txt"]}
    }
    assert build_where_filter(document_ids=["doc-1"]) == {
        "document_id": "doc-1"
    }
    assert build_where_filter(
        document_ids=["doc-1", "doc-2"],
        source_files=["policy.txt"],
    ) == {
        "$and": [
            {"document_id": {"$in": ["doc-1", "doc-2"]}},
            {"source_file": "policy.txt"},
        ]
    }


class FakeCollection:
    def __init__(self):
        self.kwargs = None

    def query(self, **kwargs):
        self.kwargs = kwargs
        return {
            "ids": [["keep", "drop"]],
            "documents": [["relevant", "weak"]],
            "metadatas": [[
                {"source_file": "policy.txt"},
                {"source_file": "other.txt"},
            ]],
            "distances": [[0.30, 0.31]],
        }


def make_store() -> VectorStore:
    store = VectorStore.__new__(VectorStore)
    store.collection = FakeCollection()
    store.db_path = Path("data/eval_chroma_db")
    return store


def test_query_uses_precomputed_embedding_filter_and_inclusive_threshold(monkeypatch):
    monkeypatch.setattr(
        vector_store,
        "embed_text",
        lambda text: pytest.fail("embed_text should not be called"),
    )
    store = make_store()

    chunks = store.query(
        question="policy",
        top_k=2,
        source_files=["policy.txt"],
        similarity_threshold=0.30,
        query_embedding=[0.1, 0.2],
    )

    assert store.collection.kwargs == {
        "query_embeddings": [[0.1, 0.2]],
        "n_results": 2,
        "where": {"source_file": "policy.txt"},
    }
    assert [chunk["chunk_id"] for chunk in chunks] == ["keep"]


def test_query_rejects_negative_threshold():
    store = make_store()

    with pytest.raises(ValueError, match="similarity_threshold"):
        store.query("question", similarity_threshold=-0.01, query_embedding=[0.1])
