from pathlib import Path
from typing import Iterable

import chromadb
from openai import OpenAI

from app.core.config import (
    CHROMA_DB_DIR,
    EMBEDDING_MODEL,
    OPENAI_API_KEY,
)
from app.core.logging_config import get_logger
from app.services.chunker import TextChunk


logger = get_logger(__name__)

def _metadata_condition(field: str, values: list[str] | None) -> dict | None:
    cleaned = list(dict.fromkeys(value for value in (values or []) if value))
    if not cleaned:
        return None
    if len(cleaned) == 1:
        return {field: cleaned[0]}
    return {field: {"$in": cleaned}}


def build_where_filter(
    document_ids: list[str] | None = None,
    source_files: list[str] | None = None,
) -> dict | None:
    conditions = [
        condition
        for condition in (
            _metadata_condition("document_id", document_ids),
            _metadata_condition("source_file", source_files),
        )
        if condition is not None
    ]
    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def embed_text(text: str) -> list[float]:
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured.")

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )

    return response.data[0].embedding


class VectorStore:
    def __init__(
        self,
        collection_name: str = "knowledge_base_cosine",
        db_path: str | Path | None = None,
    ):
        self.db_path = Path(db_path) if db_path is not None else CHROMA_DB_DIR
        self.chroma_client = chromadb.PersistentClient(
            path=str(self.db_path)
        )

        self.collection = self.chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        logger.info(
            "Vector store initialized: collection=%s",
            collection_name,
        )

    def add_chunks(
        self,
        chunks: Iterable[TextChunk],
        document_id: str | None = None,
    ) -> int:
        ids = []
        documents = []
        embeddings = []
        metadatas = []

        for chunk in chunks:
            ids.append(chunk.chunk_id)
            documents.append(chunk.text)
            embeddings.append(embed_text(chunk.text))

            metadata = {
                "source_file": chunk.source_file,
                "start_index": chunk.start_index,
                "end_index": chunk.end_index,
            }

            if document_id is not None:
                metadata["document_id"] = document_id

            metadatas.append(metadata)

        if not ids:
            logger.warning(
                "No chunks to add: document_id=%s",
                document_id,
            )
            return 0

        logger.info(
            "Adding chunks to vector store: count=%s document_id=%s",
            len(ids),
            document_id,
        )

        self.collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        logger.info(
            "Chunks added successfully: count=%s document_id=%s",
            len(ids),
            document_id,
        )

        return len(ids)

    def query(
        self,
        question: str,
        top_k: int = 3,
        document_ids: list[str] | None = None,
        source_files: list[str] | None = None,
        similarity_threshold: float | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[dict]:
        if similarity_threshold is not None and similarity_threshold < 0:
            raise ValueError("similarity_threshold cannot be negative")

        logger.info(
            "Starting vector query: question=%s top_k=%s",
            question,
            top_k,
        )

        embedding = query_embedding if query_embedding is not None else embed_text(question)

        query_kwargs = {
            "query_embeddings": [embedding],
            "n_results": top_k,
        }
        where_filter = build_where_filter(
            document_ids=document_ids,
            source_files=source_files,
        )
        if where_filter is not None:
            query_kwargs["where"] = where_filter

        results = self.collection.query(**query_kwargs)

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        ids = results.get("ids", [[]])[0]

        chunks = []

        for chunk_id, document, metadata, distance in zip(
            ids,
            documents,
            metadatas,
            distances,
        ):
            if (
                similarity_threshold is not None
                and distance > similarity_threshold
            ):
                continue
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "text": document,
                    "metadata": metadata,
                    "distance": distance,
                }
            )

        logger.info(
            "Vector query finished: question=%s top_k=%s result_count=%s",
            question,
            top_k,
            len(chunks),
        )

        return chunks

    def delete_by_document_id(
        self,
        document_id: str,
    ) -> None:
        logger.info(
            "Deleting vectors: document_id=%s",
            document_id,
        )

        self.collection.delete(
            where={"document_id": document_id}
        )

        logger.info(
            "Vectors deleted successfully: document_id=%s",
            document_id,
        )
