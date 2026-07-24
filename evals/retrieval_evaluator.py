import csv
from pathlib import Path, PureWindowsPath
from typing import Iterable


CSV_FIELDS = [
    "question_id",
    "question",
    "question_type",
    "expected_answer",
    "expected_source",
    "retrieved_sources",
    "retrieved_distances",
    "result_count",
    "hit",
    "top_k",
    "chunk_size",
    "chunk_overlap",
    "similarity_threshold",
    "answer",
    "answer_correct",
    "should_refuse",
    "refused",
    "refusal_correct",
    "notes",
]


REFUSAL_PHRASES = (
    "没有足够依据",
    "没有找到相关依据",
    "没有可靠依据",
    "知识库中没有",
    "没有文档依据",
    "无法根据提供",
    "不能确定答案",
    "no evidence",
)


def _source_name(value: str) -> str:
    return PureWindowsPath(value).name or Path(value).name


def source_hit(
    expected_source: str | None,
    retrieved_sources: Iterable[str],
) -> bool | None:
    if expected_source is None:
        return None
    expected = _source_name(expected_source).casefold()
    actual = {_source_name(source).casefold() for source in retrieved_sources}
    return expected in actual


def reciprocal_rank(
    expected_source: str | None,
    retrieved_sources: Iterable[str],
) -> float | None:
    if expected_source is None:
        return None
    expected = _source_name(expected_source).casefold()
    for rank, source in enumerate(retrieved_sources, start=1):
        if _source_name(source).casefold() == expected:
            return 1 / rank
    return 0.0


def detect_refusal(answer: str, retrieved_sources: Iterable[str]) -> bool:
    sources = list(retrieved_sources)
    if not sources:
        return True
    normalized = answer.casefold()
    return any(phrase.casefold() in normalized for phrase in REFUSAL_PHRASES)


def score_record(
    question_case: dict,
    retrieved_sources: list[str],
    retrieved_distances: list[float] | None = None,
    answer: str = "",
    *,
    top_k: int = 3,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    similarity_threshold: float | None = None,
    answer_correct: int | str = "",
    notes: str = "",
) -> dict:
    hit = source_hit(question_case.get("expected_source"), retrieved_sources)
    refused = detect_refusal(answer, retrieved_sources)
    should_refuse = bool(question_case.get("should_refuse"))
    distances = retrieved_distances or []
    return {
        "question_id": question_case["id"],
        "question": question_case["question"],
        "question_type": question_case["question_type"],
        "expected_answer": question_case.get("expected_answer", ""),
        "expected_source": question_case.get("expected_source") or "",
        "retrieved_sources": "|".join(retrieved_sources),
        "retrieved_distances": "|".join(f"{value:.6f}" for value in distances),
        "result_count": len(retrieved_sources),
        "hit": "" if hit is None else int(hit),
        "top_k": top_k,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "similarity_threshold": "" if similarity_threshold is None else similarity_threshold,
        "answer": answer,
        "answer_correct": answer_correct,
        "should_refuse": int(should_refuse),
        "refused": int(refused),
        "refusal_correct": int(refused == should_refuse),
        "notes": notes,
    }


def summarize_records(records: list[dict]) -> dict:
    hit_values = [int(row["hit"]) for row in records if row.get("hit") != ""]
    refusal_values = [int(row["refusal_correct"]) for row in records]
    answer_values = [
        int(row["answer_correct"])
        for row in records
        if row.get("answer_correct") not in ("", None)
    ]
    return {
        "question_count": len(records),
        "hit_rate": sum(hit_values) / len(hit_values) if hit_values else 0.0,
        "refusal_accuracy": (
            sum(refusal_values) / len(refusal_values) if refusal_values else 0.0
        ),
        "answer_accuracy": (
            sum(answer_values) / len(answer_values) if answer_values else None
        ),
        "average_result_count": (
            sum(int(row.get("result_count", 0)) for row in records) / len(records)
            if records
            else 0.0
        ),
    }


def write_results_csv(path: str | Path, records: list[dict]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
