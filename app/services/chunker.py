from dataclasses import dataclass
from uuid import uuid4
import re


@dataclass
class TextChunk:
    chunk_id: str
    text: str
    source_file: str
    start_index: int
    end_index: int


def split_into_sentences(text: str) -> list[str]:
    """
    把长文本按中文/英文标点切成句子。
    例如：苹果两块钱。香蕉三块钱。RAG 是一种方法。
    会切成：
    ["苹果两块钱。", "香蕉三块钱。", "RAG 是一种方法。"]
    """
    sentences = re.split(r"(?<=[。！？.!?；;])", text)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def chunk_text(
    text: str,
    source_file: str,
    chunk_size: int = 500,
    overlap: int = 50
) -> list[TextChunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")

    if overlap < 0:
        raise ValueError("overlap cannot be negative")

    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    text = text.strip()
    if not text:
        return []

    sentences = split_into_sentences(text)

    chunks: list[TextChunk] = []
    current_chunk = ""

    for sentence in sentences:
        # 如果当前句子本身就很长，先简单硬切
        if len(sentence) > chunk_size:
            start = 0
            while start < len(sentence):
                end = min(start + chunk_size, len(sentence))
                chunk_content = sentence[start:end].strip()

                if chunk_content:
                    chunks.append(
                        TextChunk(
                            chunk_id=str(uuid4()),
                            text=chunk_content,
                            source_file=source_file,
                            start_index=0,
                            end_index=0,
                        )
                    )

                if end == len(sentence):
                    break

                start = end - overlap

            continue

        # 如果加上这句话还没超过 chunk_size，就继续合并
        if len(current_chunk) + len(sentence) <= chunk_size:
            current_chunk += sentence
        else:
            # 当前 chunk 满了，先保存
            if current_chunk.strip():
                chunks.append(
                    TextChunk(
                        chunk_id=str(uuid4()),
                        text=current_chunk.strip(),
                        source_file=source_file,
                        start_index=0,
                        end_index=0,
                    )
                )

            # 给下一个 chunk 加一点 overlap
            overlap_text = current_chunk[-overlap:] if overlap > 0 else ""
            current_chunk = overlap_text + sentence

    # 保存最后一个 chunk
    if current_chunk.strip():
        chunks.append(
            TextChunk(
                chunk_id=str(uuid4()),
                text=current_chunk.strip(),
                source_file=source_file,
                start_index=0,
                end_index=0,
            )
        )

    return chunks