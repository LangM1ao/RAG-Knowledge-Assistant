from pathlib import Path
from pypdf import PdfReader


def parse_txt(file_path: Path) -> str:
    return file_path.read_text(encoding="utf-8")


def parse_pdf(file_path: Path) -> str:
    reader = PdfReader(str(file_path))
    pages = []

    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)

    return "\n".join(pages).strip()


def parse_document(file_path: Path) -> str:
    suffix = file_path.suffix.lower()

    if suffix == ".txt":
        return parse_txt(file_path)

    if suffix == ".pdf":
        return parse_pdf(file_path)

    raise ValueError("Only .txt and .pdf files are supported.")