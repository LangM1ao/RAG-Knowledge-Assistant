from app.db import chat_repository, database


def test_chat_history_is_persisted_and_returned_newest_first(monkeypatch, tmp_path):
    db_path = tmp_path / "metadata.db"
    monkeypatch.setattr(database, "METADATA_DB_PATH", db_path)

    database.init_db()
    chat_repository.create_chat_record(
        question="First question",
        answer="First answer",
        sources=[{"source_file": "one.txt"}],
    )
    chat_repository.create_chat_record(
        question="Second question",
        answer="Second answer",
        sources=[],
    )

    rows = chat_repository.list_chat_records(limit=10)

    assert [row["question"] for row in rows] == ["Second question", "First question"]
    assert rows[1]["sources"] == [{"source_file": "one.txt"}]


def test_chat_history_limit_is_clamped(monkeypatch, tmp_path):
    db_path = tmp_path / "metadata.db"
    monkeypatch.setattr(database, "METADATA_DB_PATH", db_path)
    database.init_db()

    for index in range(3):
        chat_repository.create_chat_record(
            question=f"Question {index}",
            answer="Answer",
            sources=[],
        )

    assert len(chat_repository.list_chat_records(limit=2)) == 2
