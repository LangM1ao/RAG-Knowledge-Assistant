"""Bounded source-preserving chunks with conservative hierarchical boundaries."""
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
    section_path: tuple[str, ...] = ()
    subsection_title: str | None = None
    structure_id: str | None = None
    structure_version: int = 2
    structure_reliable: bool = False


_SENTENCE_END = re.compile(r'[。！？.!?；;][ \t]*')
_LIST_ITEM = re.compile(r'^\s*(?:[-*+•]|\d+[.)、])\s+')
_DATE = r'(?:\d{1,2}[/.-]\d{4}|\d{4}(?:[/.-]\d{1,2})?)'
_DATED_TITLE = re.compile(r'^(.+?)\s+(?:'+_DATE+r')\s*[–—-]\s*(?:'+_DATE+r'|Present|Current|至今)\s*$',re.I)


def split_into_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r'(?<=[。！？.!?；;])',text) if s.strip()]


def _validate_settings(chunk_size,overlap):
    if chunk_size<=0: raise ValueError('chunk_size must be greater than 0')
    if overlap<0: raise ValueError('overlap cannot be negative')
    if overlap>=chunk_size: raise ValueError('overlap must be smaller than chunk_size')


def _heading_info(line,previous='',following='',has_parent=False):
    text=line.strip()
    if not text or _LIST_ITEM.match(text) or '|' in text: return None
    markdown=re.match(r'^(#{1,6})\s+(.+?)\s*#*$',text)
    if markdown: return len(markdown[1]),markdown[2].strip()
    numbered=re.match(r'^(\d+(?:\.\d+)*)\s+([^\n]+)$',text)
    if numbered and len(text)<=100:
        return numbered[1].count('.')+1,numbered[2].strip()
    chinese=re.match(r'^第[一二三四五六七八九十百\d]+([章节篇])\s*(.*)$',text)
    if chinese: return (2 if chinese[1]=='节' else 1),text
    if re.match(r'^[一二三四五六七八九十]+[、．]',text): return 1,text
    if re.match(r'^[(（][一二三四五六七八九十]+[)）]',text): return 2,text
    if following.strip() and re.fullmatch(r'=+',following.strip()): return 1,text
    if following.strip() and re.fullmatch(r'-{3,}',following.strip()): return 2,text
    bold=re.fullmatch(r'\*\*([^*]+)\*\*',text)
    if bold and len(text)<=100: return (2 if has_parent else 1),bold[1].strip()
    dated=_DATED_TITLE.fullmatch(text)
    if dated and len(dated[1])<=160: return (2 if has_parent else 1),dated[1].strip()
    if (2<=len(text)<=70 and len(text.split())<=8 and re.search('[A-Z]',text)
        and re.fullmatch(r'[A-Z0-9 &/():-]+',text)):
        return 1,text
    # A short title-case line preceding bullets is structural evidence, not a
    # language-specific list of known project names.
    words=text.split()
    title_case=words and sum(w[:1].isupper() or w.casefold() in {'and','of','for','the','with','in'} for w in words)/len(words)>=0.8
    if not previous.strip() and _LIST_ITEM.match(following) and 2<=len(words)<=12 and len(text)<=110 and title_case and not re.search(r'[.!?。！？]$',text):
        return (2 if has_parent else 1),text
    return None


def _spans(text,state,base_offset):
    lines=text.splitlines(keepends=True)
    start=0; offset=0; active=tuple(state)
    for n,line in enumerate(lines):
        previous=lines[n-1] if n else ''
        following=next((s for s in lines[n+1:] if s.strip()),'')
        heading=_heading_info(line,previous,following,bool(state))
        if heading:
            if offset>start: yield start,offset,active
            level,title=heading
            while state and state[-1][0]>=level: state.pop()
            state.append((level,title,f'section:{base_offset+offset}'))
            start=offset; active=tuple(state)
        offset+=len(line)
    if start<len(text): yield start,len(text),active


def _section_spans(text):
    for start,end,path in _spans(text,[],0):
        yield start,end,path[-1][1] if path else None


def _structure_boundaries(text,start,end):
    boundaries={end}; line_ends=[]; offset=start
    for line in text[start:end].splitlines(keepends=True):
        if _LIST_ITEM.match(line) and offset>start: boundaries.add(offset)
        offset+=len(line);line_ends.append(offset)
        if not line.strip(): boundaries.add(offset)
    return sorted(boundaries),line_ends


def _chunk_page(text,source_file,size,overlap,state,base_offset):
    chunks=[]
    for section_start,section_end,path in _spans(text,state,base_offset):
        structural,line_ends=_structure_boundaries(text,section_start,section_end)
        sentences=[section_start+m.end() for m in _SENTENCE_END.finditer(text[section_start:section_end])]
        start=section_start
        while start<section_end:
            hard_end=min(start+size,section_end)
            minimum=start+overlap
            preferred=[p for p in structural if minimum<p<=hard_end]
            sentence_ends=[p for p in sentences if minimum<p<=hard_end]
            complete_lines=[p for p in line_ends if minimum<p<=hard_end]
            end=hard_end if hard_end==section_end else (preferred[-1] if preferred else sentence_ends[-1] if sentence_ends else complete_lines[-1] if complete_lines else hard_end)
            if text[start:end].strip():
                names=tuple(item[1] for item in path)
                chunks.append(TextChunk(str(uuid4()),text[start:end],source_file,base_offset+start,base_offset+end,
                    chunk_index=len(chunks),section_title=names[0] if names else None,
                    section_path=names,subsection_title=names[-1] if len(names)>1 else None,
                    structure_id=path[-1][2] if path else None,structure_reliable=bool(path)))
            if end==section_end: break
            # Keep complete structural/line boundaries; overlap long forced splits.
            start=end if end in structural or end in line_ends else end-overlap
    return chunks


def chunk_text(text: str,source_file: str,chunk_size: int=500,overlap: int=50) -> list[TextChunk]:
    _validate_settings(chunk_size,overlap)
    return _chunk_page(text,source_file,chunk_size,overlap,[],0) if text.strip() else []


def chunk_document(pages: Iterable[DocumentPage],source_file: str,chunk_size: int=500,overlap: int=50) -> list[TextChunk]:
    _validate_settings(chunk_size,overlap)
    chunks=[];state=[];offset=0
    for page in pages:
        for chunk in _chunk_page(page.text,source_file,chunk_size,overlap,state,offset):
            chunk.chunk_index=len(chunks)
            chunk.page_number=page.page_number
            chunk.page_range=(page.page_number,page.page_number) if page.page_number is not None else None
            chunks.append(chunk)
        offset+=len(page.text)+1
    return chunks
