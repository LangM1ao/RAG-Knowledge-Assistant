from __future__ import annotations

import csv
import json
import time
from collections import defaultdict
from pathlib import Path

from app.services.bm25_retriever import BM25Retriever
from app.services.retriever import Retriever
from evals.retrieval_evaluator import reciprocal_rank
from evals.run_eval import (
    DEFAULT_QUESTIONS,
    PROJECT_ROOT,
    build_eval_store,
    load_question_cases,
)


DETAIL_FIELDS = [
    "question_id",
    "question",
    "question_type",
    "expected_source",
    "retrieval_mode",
    "retrieved_chunk_ids",
    "retrieved_sources",
    "hit",
    "reciprocal_rank",
    "refused",
    "refusal_correct",
    "latency_ms",
    "error_message",
]
SUMMARY_FIELDS = [
    "retrieval_mode",
    "question_type",
    "question_count",
    "answerable_count",
    "hit_rate",
    "recall_at_k",
    "mrr",
    "refusal_accuracy",
    "average_latency_ms",
]


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _summary_row(mode: str, category: str, rows: list[dict]) -> dict:
    answerable = [row for row in rows if row["expected_source"]]
    hit_rate = (
        sum(int(row["hit"]) for row in answerable) / len(answerable)
        if answerable else 0.0
    )
    mrr = (
        sum(float(row["reciprocal_rank"]) for row in answerable)
        / len(answerable)
        if answerable else 0.0
    )
    return {
        "retrieval_mode": mode,
        "question_type": category,
        "question_count": len(rows),
        "answerable_count": len(answerable),
        "hit_rate": f"{hit_rate:.6f}",
        "recall_at_k": f"{hit_rate:.6f}",
        "mrr": f"{mrr:.6f}",
        "refusal_accuracy": (
            f"{sum(int(row['refusal_correct']) for row in rows) / len(rows):.6f}"
            if rows else "0.000000"
        ),
        "average_latency_ms": (
            f"{sum(float(row['latency_ms']) for row in rows) / len(rows):.3f}"
            if rows else "0.000"
        ),
    }


def run_comparison(
    *,
    top_k: int = 3,
    similarity_threshold: float = 0.6,
    questions_path: str | Path = DEFAULT_QUESTIONS,
) -> tuple[list[dict], list[dict]]:
    store = build_eval_store(chunk_size=500, chunk_overlap=50)
    retriever = Retriever(
        vector_store=store,
        bm25_retriever=BM25Retriever(collection=store.collection),
    )
    cases = load_question_cases(questions_path)
    detail_rows = []

    for mode in ("vector", "bm25", "hybrid"):
        for case in cases:
            started = time.perf_counter()
            error_message = ""
            try:
                chunks = retriever.query(
                    case["question"],
                    retrieval_mode=mode,
                    top_k=top_k,
                    similarity_threshold=similarity_threshold,
                )
            except Exception as exc:
                chunks = []
                error_message = f"{type(exc).__name__}: {exc}"
            latency_ms = (time.perf_counter() - started) * 1000
            sources = [
                (chunk.get("metadata") or {}).get("source_file", "unknown")
                for chunk in chunks
            ]
            rr = reciprocal_rank(case.get("expected_source"), sources)
            refused = not chunks
            should_refuse = bool(case.get("should_refuse"))
            detail_rows.append(
                {
                    "question_id": case["id"],
                    "question": case["question"],
                    "question_type": case["question_type"],
                    "expected_source": case.get("expected_source") or "",
                    "retrieval_mode": mode,
                    "retrieved_chunk_ids": "|".join(
                        chunk["chunk_id"] for chunk in chunks
                    ),
                    "retrieved_sources": "|".join(sources),
                    "hit": "" if rr is None else int(rr > 0),
                    "reciprocal_rank": "" if rr is None else f"{rr:.6f}",
                    "refused": int(refused),
                    "refusal_correct": int(refused == should_refuse),
                    "latency_ms": f"{latency_ms:.3f}",
                    "error_message": error_message,
                }
            )

    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in detail_rows:
        grouped[(row["retrieval_mode"], "all")].append(row)
        grouped[(row["retrieval_mode"], row["question_type"])].append(row)
    summary_rows = [
        _summary_row(mode, category, rows)
        for (mode, category), rows in sorted(grouped.items())
    ]

    detail_path = PROJECT_ROOT / "evals" / "retrieval_mode_comparison.csv"
    summary_path = PROJECT_ROOT / "evals" / "retrieval_mode_summary.csv"
    _write_csv(detail_path, DETAIL_FIELDS, detail_rows)
    _write_csv(summary_path, SUMMARY_FIELDS, summary_rows)
    print(
        json.dumps(
            {
                "detail": str(detail_path),
                "summary": str(summary_path),
                "question_count": len(cases),
            },
            ensure_ascii=False,
        )
    )
    return detail_rows, summary_rows


if __name__ == "__main__":
    run_comparison()
