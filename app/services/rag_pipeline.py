from app.core.logging_config import get_logger
from app.services.llm_client import generate_answer
from app.services.retriever import Retriever
from app.services.vector_store import VectorStore


logger = get_logger(__name__)


def build_context(chunks: list[dict]) -> str:
    context_parts = []

    for index, chunk in enumerate(chunks, start=1):
        metadata = chunk.get("metadata") or {}

        source_file = metadata.get("source_file", "unknown")
        chunk_id = chunk.get("chunk_id", "unknown")
        text = chunk.get("text", "")

        context_parts.append(
            f"[{index}] source={source_file}, chunk_id={chunk_id}\n{text}"
        )

    return "\n\n".join(context_parts)


def answer_question(
    question: str,
    retrieval_mode: str = "vector",
    top_k: int = 3,
    similarity_threshold: float | None = None,
    document_ids: list[str] | None = None,
    source_files: list[str] | None = None,
) -> dict:
    # 记录用户提出的问题
    logger.info(
        "Answering question: question=%s top_k=%s",
        question,
        top_k,
    )

    store = VectorStore()

    query_kwargs = {
        "question": question,
        "top_k": top_k,
    }
    if similarity_threshold is not None:
        query_kwargs["similarity_threshold"] = similarity_threshold
    if document_ids:
        query_kwargs["document_ids"] = document_ids
    if source_files:
        query_kwargs["source_files"] = source_files

    chunks = Retriever(vector_store=store).query(
        retrieval_mode=retrieval_mode,
        **query_kwargs,
    )

    # 记录检索到了多少个 chunk
    logger.info(
        "Retrieved chunks: count=%s",
        len(chunks),
    )

    if not chunks:
        logger.warning(
            "No chunks retrieved, returning refusal answer."
        )

        return {
            "answer": "知识库中没有找到相关依据，因此我不能确定答案。",
            "sources": [],
        }

    context = build_context(chunks)

    messages = [
        {
            "role": "system",
            "content": (
                "你是企业知识库问答助手，只能根据提供的 context 回答。"
                "如果 context 中没有依据，请回答知识库中没有足够依据，"
                "不要编造。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Context:\n{context}\n\n"
                f"Question:\n{question}\n\n"
                "请用中文回答，并在答案末尾列出引用来源。"
            ),
        },
    ]

    logger.info(
        "Sending retrieved context to language model: chunk_count=%s",
        len(chunks),
    )

    answer = generate_answer(messages)

    logger.info(
        "Answer generated successfully."
    )

    sources = [
        {
            "chunk_id": chunk.get("chunk_id"),
            "source_file": (chunk.get("metadata") or {}).get("source_file"),
            "document_id": (chunk.get("metadata") or {}).get("document_id"),
            "distance": chunk.get("distance"),
            "retrieval_source": chunk.get("retrieval_source"),
            "rank": chunk.get("rank"),
            "vector_score": chunk.get("vector_score"),
            "vector_rank": chunk.get("vector_rank"),
            "bm25_score": chunk.get("bm25_score"),
            "bm25_rank": chunk.get("bm25_rank"),
            "rrf_score": chunk.get("rrf_score"),
            "chunk_preview": chunk.get("text", "")[:240],
        }
        for chunk in chunks
    ]

    return {
        "answer": answer,
        "sources": sources,
        "retrieval_mode": retrieval_mode,
        "retrieval_debug": sources,
    }
