from evals.keyword_retriever import KeywordRetriever, tokenize


def test_tokenize_includes_ascii_terms_numbers_and_chinese_bigrams():
    tokens = tokenize("P0 必须在 5 分钟内响应")

    assert "p0" in tokens
    assert "5" in tokens
    assert "分钟" in tokens


def test_keyword_retriever_ranks_exact_terms_above_unrelated_text():
    retriever = KeywordRetriever(
        [
            {"chunk_id": "ops", "text": "P0 的目标响应时间为 5 分钟", "metadata": {"source_file": "ops.txt"}},
            {"chunk_id": "policy", "text": "报销申请需要部门经理审批", "metadata": {"source_file": "policy.txt"}},
        ]
    )

    results = retriever.query("P0 需要几分钟响应？", top_k=2)

    assert results[0]["chunk_id"] == "ops"
    assert results[0]["keyword_score"] > results[1]["keyword_score"]


def test_keyword_retriever_empty_query_returns_no_results():
    assert KeywordRetriever([]).query("   ") == []
