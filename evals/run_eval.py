from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from app.services.chunker import chunk_text
from app.services.llm_client import generate_answer
from app.services.rag_pipeline import build_context
from app.services.vector_store import VectorStore, embed_text
from evals.retrieval_evaluator import (
    score_record,
    summarize_records,
    write_results_csv,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVAL_DB = PROJECT_ROOT / "data" / "eval_chroma_db"
DEFAULT_QUESTIONS = PROJECT_ROOT / "evals" / "test_questions.json"
DEFAULT_DEMOS = [
    PROJECT_ROOT / "demo" / "demo_knowledge_base.txt",
    PROJECT_ROOT / "demo" / "company_reimbursement_policy.txt",
    PROJECT_ROOT / "demo" / "product_ops_manual.txt",
]
SUMMARY_FIELDS = [
    "experiment",
    "chunk_size",
    "chunk_overlap",
    "top_k",
    "similarity_threshold",
    "question_count",
    "hit_rate",
    "refusal_accuracy",
    "answer_accuracy",
    "average_result_count",
    "output_file",
    "notes",
]


def assert_safe_eval_path(path: str | Path, project_root: str | Path = PROJECT_ROOT) -> Path:
    resolved = Path(path).resolve()
    expected = (Path(project_root).resolve() / "data" / "eval_chroma_db").resolve()
    if resolved != expected:
        raise ValueError(
            f"Experiment database must be data/eval_chroma_db, got: {resolved}"
        )
    return resolved


def collection_name_for(chunk_size: int, overlap: int) -> str:
    return f"week11_chunks_{chunk_size}_overlap_{overlap}"


def load_question_cases(path: str | Path = DEFAULT_QUESTIONS) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_demo_documents(paths: list[str | Path] = DEFAULT_DEMOS) -> list[tuple[str, str]]:
    return [
        (Path(path).name, Path(path).read_text(encoding="utf-8"))
        for path in paths
    ]


def build_eval_store(
    chunk_size: int,
    chunk_overlap: int,
    db_path: str | Path = DEFAULT_EVAL_DB,
) -> VectorStore:
    safe_path = assert_safe_eval_path(db_path)
    safe_path.mkdir(parents=True, exist_ok=True)
    store = VectorStore(
        collection_name=collection_name_for(chunk_size, chunk_overlap),
        db_path=safe_path,
    )
    if store.collection.count() == 0:
        for source_file, text in load_demo_documents():
            chunks = chunk_text(
                text,
                source_file=source_file,
                chunk_size=chunk_size,
                overlap=chunk_overlap,
            )
            store.add_chunks(
                chunks,
                document_id=f"eval::{source_file}",
            )
    return store


def _answer_from_chunks(question: str, chunks: list[dict]) -> str:
    if not chunks:
        return "知识库中没有找到相关依据，因此我不能确定答案。"
    context = build_context(chunks)
    messages = [
        {
            "role": "system",
            "content": (
                "你是企业知识库问答助手，只能根据 context 回答。"
                "没有依据时必须明确拒答，不要使用外部知识猜测。"
            ),
        },
        {
            "role": "user",
            "content": f"Context:\n{context}\n\nQuestion:\n{question}\n请用中文简洁回答。",
        },
    ]
    return generate_answer(messages)


def run_experiment(
    *,
    experiment: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    top_k: int = 3,
    similarity_threshold: float | None = None,
    with_answers: bool = False,
    source_files: list[str] | None = None,
    question_cases: list[dict] | None = None,
    output_path: str | Path | None = None,
) -> tuple[list[dict], dict, Path]:
    store = build_eval_store(chunk_size, chunk_overlap)
    cases = question_cases or load_question_cases()
    embedding_cache: dict[str, list[float]] = {}
    records = []

    for case in cases:
        question = case["question"]
        try:
            if question not in embedding_cache:
                embedding_cache[question] = embed_text(question)
            embedding = embedding_cache[question]
            chunks = store.query(
                question=question,
                top_k=top_k,
                source_files=source_files,
                similarity_threshold=similarity_threshold,
                query_embedding=embedding,
            )
            answer = _answer_from_chunks(question, chunks) if with_answers else ""
            sources = [
                (chunk.get("metadata") or {}).get("source_file", "unknown")
                for chunk in chunks
            ]
            distances = [float(chunk["distance"]) for chunk in chunks]
            record = score_record(
                case,
                retrieved_sources=sources,
                retrieved_distances=distances,
                answer=answer,
                top_k=top_k,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                similarity_threshold=similarity_threshold,
            )
        except Exception as exc:
            record = score_record(
                case,
                retrieved_sources=[],
                answer="",
                top_k=top_k,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                similarity_threshold=similarity_threshold,
                notes=f"ERROR: {type(exc).__name__}: {exc}",
            )
        records.append(record)

    destination = Path(output_path or PROJECT_ROOT / "evals" / f"eval_results_{experiment}.csv")
    write_results_csv(destination, records)
    summary = summarize_records(records)
    update_experiment_summary(
        experiment=experiment,
        parameters={
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "top_k": top_k,
            "similarity_threshold": similarity_threshold,
        },
        summary=summary,
        output_file=destination.name,
    )
    print(
        json.dumps(
            {"experiment": experiment, "output": str(destination), **summary},
            ensure_ascii=False,
        )
    )
    return records, summary, destination


def update_experiment_summary(
    *,
    experiment: str,
    parameters: dict,
    summary: dict,
    output_file: str,
    notes: str = "",
) -> None:
    path = PROJECT_ROOT / "evals" / "experiment_summary.csv"
    rows = []
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    rows = [row for row in rows if row.get("experiment") != experiment]
    rows.append(
        {
            "experiment": experiment,
            "chunk_size": parameters.get("chunk_size", ""),
            "chunk_overlap": parameters.get("chunk_overlap", ""),
            "top_k": parameters.get("top_k", ""),
            "similarity_threshold": (
                "" if parameters.get("similarity_threshold") is None
                else parameters["similarity_threshold"]
            ),
            "question_count": summary["question_count"],
            "hit_rate": f"{summary['hit_rate']:.6f}",
            "refusal_accuracy": f"{summary['refusal_accuracy']:.6f}",
            "answer_accuracy": (
                "" if summary["answer_accuracy"] is None
                else f"{summary['answer_accuracy']:.6f}"
            ),
            "average_result_count": f"{summary['average_result_count']:.6f}",
            "output_file": output_file,
            "notes": notes,
        }
    )
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def run_cli(args: argparse.Namespace) -> None:
    if args.mode == "baseline":
        run_experiment(experiment="baseline", with_answers=args.with_answers)
    elif args.mode == "chunk":
        for size, overlap in ((300, 50), (500, 50), (800, 100)):
            run_experiment(
                experiment=f"chunk_{size}_{overlap}",
                chunk_size=size,
                chunk_overlap=overlap,
            )
    elif args.mode == "top-k":
        for top_k in (3, 5, 8):
            run_experiment(experiment=f"top_k_{top_k}", top_k=top_k)
    elif args.mode in {"threshold", "threshold-probe"}:
        thresholds = args.thresholds if args.mode == "threshold" else [None]
        for threshold in thresholds:
            label = "probe" if threshold is None else str(threshold).replace(".", "_")
            run_experiment(
                experiment=f"threshold_{label}",
                similarity_threshold=threshold,
                top_k=8,
            )
    elif args.mode == "filter":
        cases = load_question_cases()
        selected = [case for case in cases if case["id"] in {"q001", "q005"}]
        run_experiment(
            experiment="filter_reimbursement",
            source_files=["company_reimbursement_policy.txt"],
            question_cases=selected,
        )
        run_experiment(
            experiment="filter_operations",
            source_files=["product_ops_manual.txt"],
            question_cases=selected,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run isolated Week11 RAG evaluations.")
    parser.add_argument(
        "mode",
        choices=("baseline", "chunk", "top-k", "threshold-probe", "threshold", "filter"),
    )
    parser.add_argument("--with-answers", action="store_true")
    parser.add_argument("--thresholds", nargs="+", type=float, default=[])
    return parser


if __name__ == "__main__":
    run_cli(build_parser().parse_args())
