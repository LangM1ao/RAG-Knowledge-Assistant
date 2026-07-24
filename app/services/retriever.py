from __future__ import annotations

from copy import deepcopy

from app.core.config import (
    BM25_CANDIDATE_K,
    RRF_K,
    VECTOR_CANDIDATE_K,
)
from app.services.bm25_retriever import BM25Retriever
from app.services.vector_store import VectorStore


RETRIEVAL_MODES = {"vector", "bm25", "hybrid"}


def _normalize_vector_results(chunks: list[dict]) -> list[dict]:
    results = []
    for rank, chunk in enumerate(chunks, start=1):
        distance = chunk.get("distance")
        results.append(
            {
                **chunk,
                "score": distance,
                "rank": rank,
                "retrieval_source": "vector",
                "vector_score": distance,
                "vector_rank": rank,
                "bm25_score": None,
                "bm25_rank": None,
                "rrf_score": None,
            }
        )
    return results


def reciprocal_rank_fusion(
    vector_results: list[dict],
    bm25_results: list[dict],
    *,
    top_k: int,
    rrf_k: int = 60,
) -> list[dict]:
    fused: dict[str, dict] = {}

    for source, results in (
        ("vector", vector_results),
        ("bm25", bm25_results),
    ):
        for rank, original in enumerate(results, start=1):
            chunk_id = original["chunk_id"]
            item = fused.setdefault(
                chunk_id,
                {
                    **deepcopy(original),
                    "retrieval_source": "hybrid",
                    "vector_score": None,
                    "vector_rank": None,
                    "bm25_score": None,
                    "bm25_rank": None,
                    "rrf_score": 0.0,
                    "distance": original.get("distance"),
                },
            )
            item["rrf_score"] += 1 / (rrf_k + rank)
            if source == "vector":
                vector_score = original.get(
                    "vector_score",
                    original.get("distance"),
                )
                item["vector_score"] = vector_score
                item["vector_rank"] = rank
                item["distance"] = original.get("distance", vector_score)
            else:
                item["bm25_score"] = original.get(
                    "bm25_score",
                    original.get("score"),
                )
                item["bm25_rank"] = rank

    ranked = sorted(
        fused.values(),
        key=lambda item: (
            item["rrf_score"],
            item["vector_rank"] is not None and item["bm25_rank"] is not None,
        ),
        reverse=True,
    )
    for rank, item in enumerate(ranked[:top_k], start=1):
        item["rank"] = rank
        item["score"] = item["rrf_score"]
    return ranked[:top_k]


class Retriever:
    def __init__(
        self,
        vector_store: VectorStore | None = None,
        bm25_retriever: BM25Retriever | None = None,
    ):
        self.vector_store = vector_store or VectorStore()
        self.bm25_retriever = bm25_retriever

    def _bm25(self) -> BM25Retriever:
        if self.bm25_retriever is None:
            self.bm25_retriever = BM25Retriever(
                collection=self.vector_store.collection
            )
        return self.bm25_retriever

    def query(
        self,
        question: str,
        *,
        retrieval_mode: str = "vector",
        top_k: int = 3,
        similarity_threshold: float | None = None,
        document_ids: list[str] | None = None,
        source_files: list[str] | None = None,
    ) -> list[dict]:
        if retrieval_mode not in RETRIEVAL_MODES:
            raise ValueError(
                f"Unsupported retrieval mode: {retrieval_mode}"
            )

        common = {"question": question}
        if document_ids:
            common["document_ids"] = document_ids
        if source_files:
            common["source_files"] = source_files
        vector_options = {**common, "top_k": top_k}
        if similarity_threshold is not None:
            vector_options["similarity_threshold"] = similarity_threshold
        if retrieval_mode == "vector":
            return _normalize_vector_results(
                self.vector_store.query(**vector_options)
            )
        if retrieval_mode == "bm25":
            return self._bm25().query(
                **common,
                top_k=top_k,
            )

        vector_options["top_k"] = max(top_k, VECTOR_CANDIDATE_K)
        vector_results = _normalize_vector_results(
            self.vector_store.query(**vector_options)
        )
        bm25_results = self._bm25().query(
            **common,
            top_k=max(top_k, BM25_CANDIDATE_K),
        )
        return reciprocal_rank_fusion(
            vector_results,
            bm25_results,
            top_k=top_k,
            rrf_k=RRF_K,
        )
