from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from app.core.logging_config import get_logger
from app.services.vector_store import VectorStore
from app.services.query_normalizer import normalize_query


logger = get_logger(__name__)

IDENTIFIER_PATTERN = re.compile(r"[a-z0-9_][a-z0-9_.:-]*")
CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    """Tokenize English identifiers and Chinese text without a heavy dependency."""
    normalized = normalize_query(text)
    tokens = [token.rstrip(".:-") for token in IDENTIFIER_PATTERN.findall(normalized)]
    tokens = [token for token in tokens if token]
    for sequence in CHINESE_PATTERN.findall(normalized):
        if len(sequence) == 1:
            tokens.append(sequence)
        else:
            tokens.extend(
                sequence[index:index + 2]
                for index in range(len(sequence) - 1)
            )
    return tokens


def _matches_filter(
    metadata: dict[str, Any],
    document_ids: list[str] | None,
    source_files: list[str] | None,
) -> bool:
    if document_ids and metadata.get("document_id") not in document_ids:
        return False
    if source_files and metadata.get("source_file") not in source_files:
        return False
    return True


class BM25Retriever:
    """Build a small in-memory BM25 index from ChromaDB's persisted chunks."""

    def __init__(
        self,
        collection=None,
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ):
        self.collection = collection or VectorStore().collection
        self.k1 = k1
        self.b = b

    def _load_chunks(
        self,
        document_ids: list[str] | None = None,
        source_files: list[str] | None = None,
    ) -> list[dict]:
        payload = self.collection.get(include=["documents", "metadatas"])
        ids = payload.get("ids") or []
        documents = payload.get("documents") or []
        metadatas = payload.get("metadatas") or []
        chunks = []
        for chunk_id, text, metadata in zip(ids, documents, metadatas):
            normalized_metadata = metadata or {}
            if not _matches_filter(
                normalized_metadata,
                document_ids,
                source_files,
            ):
                continue
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "text": text or "",
                    "metadata": normalized_metadata,
                }
            )
        return chunks

    @staticmethod
    def _idf(total: int, containing: int) -> float:
        return math.log(
            1 + (total - containing + 0.5) / (containing + 0.5)
        )

    def query(
        self,
        question: str,
        top_k: int = 3,
        document_ids: list[str] | None = None,
        source_files: list[str] | None = None,
    ) -> list[dict]:
        query_tokens = list(dict.fromkeys(token for token in tokenize(question) if token not in {"the", "a", "an", "is", "are", "of", "for", "to", "in", "on", "and", "how", "what", "which", "does", "do", "can", "please", "什么", "哪些", "如何", "请问"}))
        self.last_debug = {"query_terms": query_tokens, "candidates": [], "filtered": []}
        identifier_terms = [term for term in query_tokens if "_" in term or (re.search(r"\d",term) and re.search(r"[-.:]",term))]
        self.last_debug["identifier_terms"] = identifier_terms
        if not query_tokens:
            self.last_debug["empty_reason"] = "no_effective_query_terms"
            return []

        try:
            chunks = self._load_chunks(document_ids, source_files)
        except Exception as exc:
            self.last_debug["error"] = type(exc).__name__
            logger.warning("BM25 load failed: type=%s", type(exc).__name__)
            raise RuntimeError("BM25 index could not be read") from None

        if not chunks:
            logger.info("BM25 query skipped because the filtered index is empty.")
            return []

        tokenized = [tokenize(chunk["text"]) for chunk in chunks]
        lengths = [len(tokens) for tokens in tokenized]
        average_length = sum(lengths) / len(lengths) if lengths else 0.0
        if average_length == 0:
            return []

        term_frequencies = [Counter(tokens) for tokens in tokenized]
        document_frequency: Counter[str] = Counter()
        for tokens in tokenized:
            document_frequency.update(set(tokens))

        scored = []
        total = len(chunks)
        for index, chunk in enumerate(chunks):
            score = 0.0
            frequencies = term_frequencies[index]
            length = lengths[index]
            for token in query_tokens:
                frequency = frequencies.get(token, 0)
                if frequency == 0:
                    continue
                denominator = frequency + self.k1 * (
                    1 - self.b + self.b * length / average_length
                )
                score += (
                    self._idf(total, document_frequency[token])
                    * frequency
                    * (self.k1 + 1)
                    / denominator
                )
            matched = [token for token in query_tokens if frequencies.get(token, 0)]
            identifier_match = not identifier_terms or bool(set(identifier_terms) & set(matched))
            if score > 0 and matched and identifier_match:
                scored.append((score, {**chunk, "matched_terms": matched, "content_match": True}))
            else:
                self.last_debug["filtered"].append({"chunk_id": chunk["chunk_id"], "reason": "identifier_not_matched" if not identifier_match else "no_body_term_match"})

        scored.sort(key=lambda item: (-item[0], item[1]["metadata"].get("document_id", ""), item[1]["chunk_id"]))
        results = []
        for rank, (score, chunk) in enumerate(scored[:top_k], start=1):
            results.append(
                {
                    **chunk,
                    "score": score,
                    "rank": rank,
                    "retrieval_source": "bm25",
                    "vector_score": None,
                    "vector_rank": None,
                    "bm25_score": score,
                    "bm25_rank": rank,
                    "rrf_score": None,
                    "distance": None,
                }
            )

        self.last_debug["candidates"] = [{"chunk_id": r["chunk_id"], "document_id": r["metadata"].get("document_id"), "rank": r["rank"], "score": r["bm25_score"], "matched_terms": r["matched_terms"], "content_match": True} for r in results]
        if not results:
            self.last_debug["empty_reason"] = "no_effective_lexical_match"

        logger.info(
            "BM25 query finished: top_k=%s candidates=%s results=%s",
            top_k,
            len(chunks),
            len(results),
        )
        return results
