from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]

load_dotenv(BASE_DIR / ".env")

APP_NAME = "RAG Knowledge Base Assistant"

UPLOAD_DIR = BASE_DIR / os.getenv("UPLOAD_DIR", "data/uploads")
CHROMA_DB_DIR = BASE_DIR / os.getenv("CHROMA_DB_DIR", "data/chroma_db")
METADATA_DB_PATH = BASE_DIR / os.getenv("METADATA_DB_PATH", "data/metadata.db")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-5.5")

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))
TOP_K = int(os.getenv("TOP_K", "3"))
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.6"))
DEFAULT_RETRIEVAL_MODE = os.getenv("DEFAULT_RETRIEVAL_MODE", "vector")
VECTOR_CANDIDATE_K = int(os.getenv("VECTOR_CANDIDATE_K", "8"))
BM25_CANDIDATE_K = int(os.getenv("BM25_CANDIDATE_K", "8"))
RRF_K = int(os.getenv("RRF_K", "60"))

# 默认启用答案依据校验；设为 false 可恢复原有问答流程。
ANSWER_VERIFICATION_ENABLED = os.getenv("ANSWER_VERIFICATION_ENABLED", "true").strip().lower() in {
    "true", "1", "yes", "on"
}

# 仅受信任开发环境开启；还需要请求 debug=true。
RETRIEVAL_DEBUG_ENABLED = os.getenv("RETRIEVAL_DEBUG_ENABLED", "false").strip().lower() in {"true", "1", "yes", "on"}
CONTEXT_MAX_CHARS = max(500, int(os.getenv("CONTEXT_MAX_CHARS", "6000")))
CONTEXT_MAX_CHUNKS = max(1, int(os.getenv("CONTEXT_MAX_CHUNKS", "6")))
