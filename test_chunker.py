from app.services.chunker import chunk_text

text = "苹果两块钱。香蕉三块钱。RAG 是一种检索增强生成方法。"
chunks = chunk_text(text, source_file="demo.txt", chunk_size=20, overlap=5)

for chunk in chunks:
    print(chunk)