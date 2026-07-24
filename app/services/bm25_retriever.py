from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from app.core.logging_config import get_logger
from app.services.vector_store import VectorStore


logger = get_logger(__name__)

IDENTIFIER_PATTERN = re.compile(r"[a-z0-9_][a-z0-9_.:-]*")
CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    """Tokenize English identifiers and Chinese text without a heavy dependency."""
    normalized = text.casefold()
    tokens = IDENTIFIER_PATTERN.findall(normalized)
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
        query_tokens = tokenize(question)
        if not query_tokens:
            return []

        try:
            chunks = self._load_chunks(document_ids, source_files)
        except Exception:
            logger.exception("Failed to load chunks for BM25 index.")
            return []

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
            if score > 0:
                scored.append((score, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
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

        logger.info(
            "BM25 query finished: top_k=%s candidates=%s results=%s",
            top_k,
            len(chunks),
            len(results),
        )
        return results
