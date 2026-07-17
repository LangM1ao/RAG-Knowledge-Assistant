import json
from pathlib import Path

import pytest

from evals.run_eval import (
    assert_safe_eval_path,
    collection_name_for,
    load_demo_documents,
    load_question_cases,
)


def test_assert_safe_eval_path_accepts_only_eval_chroma_directory(tmp_path):
    project_root = tmp_path / "project"
    safe = project_root / "data" / "eval_chroma_db"

    assert assert_safe_eval_path(safe, project_root) == safe.resolve()
    with pytest.raises(ValueError, match="eval_chroma_db"):
        assert_safe_eval_path(project_root / "data" / "chroma_db", project_root)


def test_collection_name_is_deterministic():
    assert collection_name_for(500, 50) == "week11_chunks_500_overlap_50"


def test_load_question_cases_and_demo_documents(tmp_path):
    questions_path = tmp_path / "questions.json"
    questions_path.write_text(
        json.dumps([{"id": "q001", "question": "hello"}]),
        encoding="utf-8",
    )
    demo_path = tmp_path / "demo.txt"
    demo_path.write_text("demo content", encoding="utf-8")

    assert load_question_cases(questions_path)[0]["id"] == "q001"
    assert load_demo_documents([demo_path]) == [("demo.txt", "demo content")]
