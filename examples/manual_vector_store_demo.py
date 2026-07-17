from app.services.chunker import chunk_text
from app.services.vector_store import VectorStore


text = "苹果价格是两块钱。香蕉价格是三块钱。"
chunks = chunk_text(
    text,
    source_file="demo.txt",
    chunk_size=20,
    overlap=5,
)

store = VectorStore()
count = store.add_chunks(chunks)
print(count)
