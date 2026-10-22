from dataclasses import dataclass
from pathlib import Path
from pypdf import PdfReader


@dataclass(frozen=True)
class DocumentPage:
    text: str
    page_number: int | None = None


def parse_txt(file_path: Path) -> str:
    return file_path.read_text(encoding='utf-8')


def parse_document_pages(file_path: Path) -> list[DocumentPage]:
    suffix = file_path.suffix.lower()
    if suffix == '.txt':
        return [DocumentPage(parse_txt(file_path))]
    if suffix == '.pdf':
        reader = PdfReader(str(file_path))
        return [DocumentPage(page.extract_text() or '', index)
                for index, page in enumerate(reader.pages, start=1)]
    raise ValueError('Only .txt and .pdf files are supported.')


def parse_pdf(file_path: Path) -> str:
    return '\n'.join(page.text for page in parse_document_pages(file_path)).strip()


def parse_document(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == '.txt':
        return parse_txt(file_path)
    if suffix == '.pdf':
        return parse_pdf(file_path)
    raise ValueError('Only .txt and .pdf files are supported.')
