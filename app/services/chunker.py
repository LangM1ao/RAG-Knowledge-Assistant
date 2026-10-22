"""Structure-aware, lossless character chunks with source offsets."""
from dataclasses import dataclass
import re
from typing import Iterable
from uuid import uuid4

from app.services.document_parser import DocumentPage


@dataclass
class TextChunk:
    chunk_id: str
    text: str
    source_file: str
    start_index: int
    end_index: int
    chunk_index: int = 0
    section_title: str | None = None
    page_number: int | None = None
    page_range: tuple[int, int] | None = None


_SENTENCE_END = re.compile(r'[\u3002\uff01\uff1f.!?\uff1b;][ \t]*')
_HEADING = re.compile(
    r'^(?:#{1,6}\s+.+|\u7b2c[\u4e00-\u9fff\d]+[\u7ae0\u8282\u7bc7].*|'
    r'(?:Chapter|Section)\s+\d+.*|\d+(?:\.\d+)+\s+.+|'
    r'[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+[\u3001\uff0e].+)$',
    re.IGNORECASE,
)
_LIST_ITEM = re.compile(r'^\s*(?:[-*+\u2022]|\d+[.)\u3001])\s+')


def split_into_sentences(text: str) -> list[str]:
    """Keep the legacy sentence helper; chunk offsets use untouched source text."""
    return [part.strip() for part in re.split(r'(?<=[\u3002\uff01\uff1f.!?\uff1b;])', text) if part.strip()]


def _validate_settings(chunk_size: int, overlap: int) -> None:
    if chunk_size <= 0:
        raise ValueError('chunk_size must be greater than 0')
    if overlap < 0:
        raise ValueError('overlap cannot be negative')
    if overlap >= chunk_size:
        raise ValueError('overlap must be smaller than chunk_size')


def _is_heading(text: str) -> bool:
    if _HEADING.fullmatch(text):
        return True
    # Generic short uppercase headings, including CV sections, without hardcoded names.
    return bool(2 <= len(text) <= 70 and len(text.split()) <= 8
                and re.search(r'[A-Z]', text) and re.fullmatch(r'[A-Z0-9 &/():-]+', text)
                and not _LIST_ITEM.match(text))


def _section_spans(text: str):
    start, offset, title = 0, 0, None
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if _is_heading(stripped):
            if offset > start:
                yield start, offset, title
            start = offset
            title = re.sub(r'^#{1,6}\s+', '', stripped).rstrip('#').strip()
        offset += len(line)
    if start < len(text):
        yield start, len(text), title


def _structure_boundaries(text: str, start: int, end: int) -> list[int]:
    """Prefer whole paragraphs and list items before sentence/character fallback."""
    boundaries = set()
    offset = start
    for line in text[start:end].splitlines(keepends=True):
        if _LIST_ITEM.match(line) and offset > start:
            boundaries.add(offset)
        offset += len(line)
        if not _is_heading(line.strip()):
            boundaries.add(offset)
    boundaries.add(end)
    return sorted(boundaries)


def chunk_text(text: str, source_file: str, chunk_size: int = 500, overlap: int = 50) -> list[TextChunk]:
    _validate_settings(chunk_size, overlap)
    if not text.strip():
        return []
    chunks = []
    for section_start, section_end, title in _section_spans(text):
        structural = _structure_boundaries(text, section_start, section_end)
        sentences = [section_start + match.end() for match in _SENTENCE_END.finditer(text[section_start:section_end])]
        start = section_start
        while start < section_end:
            hard_end = min(start + chunk_size, section_end)
            # A boundary must advance beyond the overlap to guarantee progress.
            minimum_end = start + overlap
            preferred = [point for point in structural if minimum_end < point <= hard_end]
            sentence_ends = [point for point in sentences if minimum_end < point <= hard_end]
            end = hard_end if hard_end == section_end else (
                preferred[-1] if preferred else sentence_ends[-1] if sentence_ends else hard_end
            )
            chunks.append(TextChunk(str(uuid4()), text[start:end], source_file, start, end,
                                    chunk_index=len(chunks), section_title=title))
            if end == section_end:
                break
            # Structural boundaries stand alone; overlap is for forced long-block splits.
            start = end if end in structural else end - overlap
    return chunks


def chunk_document(pages: Iterable[DocumentPage], source_file: str,
                   chunk_size: int = 500, overlap: int = 50) -> list[TextChunk]:
    """Offsets address '\\n'.join(page.text); PDF chunks never mix physical pages."""
    _validate_settings(chunk_size, overlap)
    chunks, offset = [], 0
    section_title = None
    for page in pages:
        page_chunks = chunk_text(page.text, source_file, chunk_size, overlap)
        for chunk in page_chunks:
            chunk.start_index += offset
            chunk.end_index += offset
            chunk.chunk_index = len(chunks)
            chunk.page_number = page.page_number
            chunk.page_range = (page.page_number, page.page_number) if page.page_number is not None else None
            if chunk.section_title is None:
                chunk.section_title = section_title
            else:
                section_title = chunk.section_title
            chunks.append(chunk)
        offset += len(page.text) + 1
    return chunks
