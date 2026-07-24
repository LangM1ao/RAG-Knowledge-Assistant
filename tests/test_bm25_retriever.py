from app.services.bm25_retriever import BM25Retriever, tokenize


class FakeCollection:
    def __init__(self, records):
        self.records = records

    def get(self, include=None):
        return {
            "ids": [record["chunk_id"] for record in self.records],
            "documents": [record["text"] for record in self.records],
            "metadatas": [record["metadata"] for record in self.records],
        }


def make_records():
    return [
        {
            "chunk_id": "ops",
            "text": "P0 事故需要在 5 分钟内响应，错误码 ERR_CONNECTION_104 表示连接失败。",
            "metadata": {
                "document_id": "doc-ops",
                "source_file": "ops.txt",
                "start_index": 0,
                "end_index": 50,
            },
        },
        {
            "chunk_id": "config",
            "text": "API_TIMEOUT_MS 默认值为 30000，可以在服务配置文件中修改。",
            "metadata": {
                "document_id": "doc-config",
                "source_file": "config.txt",
                "start_index": 0,
                "end_index": 40,
            },
        },
        {
            "chunk_id": "travel",
            "text": "员工出差住宿费用上限为每晚 500 元。",
            "metadata": {
                "document_id": "doc-policy",
                "source_file": "policy.txt",
                "start_index": 0,
                "end_index": 30,
            },
        },
    ]


def test_tokenize_preserves_identifiers_and_normalizes_case():
    tokens = tokenize("ERR_CONNECTION_104 和 Api.Timeout-MS")

    assert "err_connection_104" in tokens
    assert "api.timeout-ms" in tokens


def test_bm25_ranks_exact_error_code_first_and_preserves_metadata():
    retriever = BM25Retriever(collection=FakeCollection(make_records()))

    results = retriever.query("ERR_CONNECTION_104 如何处理？", top_k=2)

    assert results[0]["chunk_id"] == "ops"
    assert results[0]["metadata"]["document_id"] == "doc-ops"
    assert results[0]["metadata"]["source_file"] == "ops.txt"
    assert results[0]["bm25_score"] > 0
    assert results[0]["bm25_rank"] == 1
    assert results[0]["retrieval_source"] == "bm25"


def test_bm25_supports_chinese_query_top_k_and_document_filter():
    retriever = BM25Retriever(collection=FakeCollection(make_records()))

    results = retriever.query(
        "住宿费用限制",
        top_k=1,
        document_ids=["doc-policy"],
    )

    assert [result["chunk_id"] for result in results] == ["travel"]


def test_bm25_supports_source_file_filter():
    retriever = BM25Retriever(collection=FakeCollection(make_records()))

    results = retriever.query(
        "默认配置",
        top_k=3,
        source_files=["config.txt"],
    )

    assert [result["chunk_id"] for result in results] == ["config"]


def test_bm25_empty_index_empty_query_and_no_match_are_safe():
    empty = BM25Retriever(collection=FakeCollection([]))
    populated = BM25Retriever(collection=FakeCollection(make_records()))

    assert empty.query("错误码") == []
    assert populated.query("   ") == []
    assert populated.query("完全不存在的XYZ999") == []


def test_bm25_reads_collection_fresh_after_upload_delete_and_rebuild():
    collection = FakeCollection(make_records()[:1])
    retriever = BM25Retriever(collection=collection)
    assert retriever.query("ERR_CONNECTION_104")[0]["chunk_id"] == "ops"

    collection.records = make_records()[1:]
    assert retriever.query("ERR_CONNECTION_104") == []
    assert retriever.query("API_TIMEOUT_MS")[0]["chunk_id"] == "config"

    collection.records = make_records()
    assert retriever.query("ERR_CONNECTION_104")[0]["chunk_id"] == "ops"
