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
