import csv

from evals.retrieval_evaluator import (
    CSV_FIELDS,
    detect_refusal,
    score_record,
    source_hit,
    summarize_records,
    write_results_csv,
)


def test_source_hit_normalizes_paths_and_skips_out_of_scope():
    assert source_hit("policy.txt", [r"C:\demo\policy.txt"]) is True
    assert source_hit("policy.txt", ["other.txt"]) is False
    assert source_hit(None, []) is None


def test_detect_refusal_uses_empty_sources_or_explicit_language():
    assert detect_refusal("anything", []) is True
    assert detect_refusal("知识库中没有足够依据。", ["weak.txt"]) is True
    assert detect_refusal("没有文档依据，无法回答这个问题。", ["weak.txt"]) is True
    assert detect_refusal("答案是 10 天。", ["policy.txt"]) is False


def test_score_and_summary_use_correct_denominators():
    hit = score_record(
        {"id": "q1", "question": "q", "question_type": "direct", "expected_source": "policy.txt", "expected_answer": "a", "should_refuse": False},
        retrieved_sources=["policy.txt"],
        answer="a",
    )
    refused = score_record(
        {"id": "q2", "question": "q", "question_type": "out", "expected_source": None, "expected_answer": "refuse", "should_refuse": True},
        retrieved_sources=[],
        answer="no evidence",
    )

    summary = summarize_records([hit, refused])

    assert hit["hit"] == 1
    assert refused["hit"] == ""
    assert refused["refusal_correct"] == 1
    assert summary["hit_rate"] == 1.0
    assert summary["refusal_accuracy"] == 1.0


def test_write_results_csv_has_stable_headers(tmp_path):
    path = tmp_path / "results.csv"
    record = score_record(
        {"id": "q1", "question": "q", "question_type": "direct", "expected_source": "policy.txt", "expected_answer": "a", "should_refuse": False},
        retrieved_sources=["policy.txt"],
        retrieved_distances=[0.12],
    )

    write_results_csv(path, [record])

    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == CSV_FIELDS
        assert list(reader)[0]["question_id"] == "q1"
