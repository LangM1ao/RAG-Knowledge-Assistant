import pytest

from app.services.retriever import Retriever, reciprocal_rank_fusion


def result(chunk_id, source, score, document_id="doc-1"):
    item = {
        "chunk_id": chunk_id,
        "text": f"text-{chunk_id}",
        "metadata": {
            "document_id": document_id,
            "source_file": f"{document_id}.txt",
        },
    }
    if source == "vector":
        item["distance"] = score
    else:
        item["bm25_score"] = score
    return item


class FakeVectorStore:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def query(self, **kwargs):
        self.calls.append(kwargs)
        return self.results


class FakeBM25:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def query(self, **kwargs):
        self.calls.append(kwargs)
        return self.results


def test_rrf_deduplicates_and_rewards_chunks_found_by_both_branches():
    vector = [result("shared", "vector", 0.1), result("vector-only", "vector", 0.2)]
    bm25 = [result("bm25-only", "bm25", 9.0), result("shared", "bm25", 8.0)]

    fused = reciprocal_rank_fusion(vector, bm25, top_k=3, rrf_k=60)

    assert len(fused) == 3
    assert fused[0]["chunk_id"] == "shared"
    assert fused[0]["vector_rank"] == 1
    assert fused[0]["bm25_rank"] == 2
    assert fused[0]["vector_score"] == pytest.approx(0.1)
    assert fused[0]["bm25_score"] == pytest.approx(8.0)
    assert fused[0]["rrf_score"] == pytest.approx(1 / 61 + 1 / 62)
    assert fused[0]["retrieval_source"] == "hybrid"


def test_retriever_supports_vector_bm25_and_hybrid_modes():
    vector = FakeVectorStore([result("v", "vector", 0.1)])
    bm25 = FakeBM25([result("b", "bm25", 3.0)])
    retriever = Retriever(vector_store=vector, bm25_retriever=bm25)

    assert retriever.query("q", retrieval_mode="vector")[0]["chunk_id"] == "v"
    assert retriever.query("q", retrieval_mode="bm25")[0]["chunk_id"] == "b"
    hybrid = retriever.query("q", retrieval_mode="hybrid", top_k=2)
    assert {item["chunk_id"] for item in hybrid} == {"v", "b"}


def test_retriever_passes_filters_and_threshold_to_correct_branches():
    vector = FakeVectorStore([])
    bm25 = FakeBM25([])
    retriever = Retriever(vector_store=vector, bm25_retriever=bm25)

    retriever.query(
        "q",
        retrieval_mode="hybrid",
        top_k=2,
        similarity_threshold=0.6,
        document_ids=["doc-1"],
        source_files=["doc-1.txt"],
    )

    assert vector.calls[0]["similarity_threshold"] == 0.6
    assert vector.calls[0]["document_ids"] == ["doc-1"]
    assert bm25.calls[0]["document_ids"] == ["doc-1"]
    assert "similarity_threshold" not in bm25.calls[0]


def test_retriever_handles_one_or_both_empty_branches():
    vector = FakeVectorStore([result("v", "vector", 0.1)])
    empty = FakeBM25([])
    retriever = Retriever(vector_store=vector, bm25_retriever=empty)

    assert retriever.query("q", retrieval_mode="hybrid")[0]["chunk_id"] == "v"

    both_empty = Retriever(vector_store=FakeVectorStore([]), bm25_retriever=FakeBM25([]))
    assert both_empty.query("q", retrieval_mode="hybrid") == []


def test_retriever_rejects_unknown_mode():
    retriever = Retriever(vector_store=FakeVectorStore([]), bm25_retriever=FakeBM25([]))

    with pytest.raises(ValueError, match="Unsupported retrieval mode"):
        retriever.query("q", retrieval_mode="unknown")
