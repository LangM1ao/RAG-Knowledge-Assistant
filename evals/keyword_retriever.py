import re
from collections import Counter


def tokenize(text: str) -> list[str]:
    normalized = text.casefold()
    tokens = re.findall(r"[a-z0-9]+", normalized)
    for sequence in re.findall(r"[\u4e00-\u9fff]+", normalized):
        if len(sequence) == 1:
            tokens.append(sequence)
        else:
            tokens.extend(sequence[index:index + 2] for index in range(len(sequence) - 1))
    return tokens


class KeywordRetriever:
    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        self.chunk_tokens = [Counter(tokenize(chunk.get("text", ""))) for chunk in chunks]

    def query(self, question: str, top_k: int = 3) -> list[dict]:
        query_tokens = set(tokenize(question))
        if not query_tokens:
            return []

        scored = []
        for chunk, counts in zip(self.chunks, self.chunk_tokens):
            overlap = query_tokens.intersection(counts)
            score = float(len(overlap)) + 0.01 * sum(counts[token] for token in overlap)
            scored.append({**chunk, "keyword_score": score})

        scored.sort(key=lambda item: item["keyword_score"], reverse=True)
        return scored[:top_k]
