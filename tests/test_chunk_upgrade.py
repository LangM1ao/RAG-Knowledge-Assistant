from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import chunker, document_parser, vector_store


def assert_exact_coverage(text, chunks, limit):
    covered = set()
    for index, chunk in enumerate(chunks):
        assert 0 < len(chunk.text) <= limit
        assert chunk.text == text[chunk.start_index:chunk.end_index]
        assert chunk.chunk_index == index
        covered.update(range(chunk.start_index, chunk.end_index))
    assert covered == set(range(len(text)))
    assert [c.start_index for c in chunks] == sorted(c.start_index for c in chunks)


def test_long_sentence_does_not_reorder_or_lose_original_characters():
    text = '  Intro.\n\n' + '\u957f' * 65 + '\u3002\n\u7ed3\u5c3e\u3002  '
    chunks = chunker.chunk_text(text, 'sample.txt', chunk_size=30, overlap=5)
    assert_exact_coverage(text, chunks, 30)
    assert chunks[0].text.startswith('  Intro.')
    assert chunks[-1].text.endswith('  ')


def test_sections_and_lists_preserve_layout_and_never_cross_heading():
    text = '# Alpha\nFirst paragraph.\n\n- one\n- two\n\n# Beta\nSecond paragraph.\n'
    chunks = chunker.chunk_text(text, 'sample.txt', chunk_size=60, overlap=5)
    assert_exact_coverage(text, chunks, 60)
    assert len(chunks) == 2
    assert chunks[0].section_title == 'Alpha'
    assert chunks[1].section_title == 'Beta'
    assert chunks[0].text.endswith('- two\n\n')
    assert chunks[1].text.startswith('# Beta')
    assert all(c.page_number is None and c.page_range is None for c in chunks)


def test_sentence_overlap_respects_hard_limit():
    text = 'First sentence. Second sentence. Third sentence. Fourth sentence.'
    chunks = chunker.chunk_text(text, 'sample.txt', chunk_size=25, overlap=8)
    assert_exact_coverage(text, chunks, 25)
    assert any(left.end_index > right.start_index for left, right in zip(chunks, chunks[1:]))


def test_pdf_uses_physical_page_numbers_including_empty_pages(monkeypatch, tmp_path):
    monkeypatch.setattr(document_parser, 'PdfReader', lambda path: SimpleNamespace(pages=[
        SimpleNamespace(extract_text=lambda: 'Page one.'),
        SimpleNamespace(extract_text=lambda: ''),
        SimpleNamespace(extract_text=lambda: 'Page three.'),
    ]))
    pages = document_parser.parse_document_pages(tmp_path / 'sample.pdf')
    assert [page.page_number for page in pages] == [1, 2, 3]
    chunks = chunker.chunk_document(pages, 'sample.pdf', chunk_size=100, overlap=5)
    assert [chunk.page_number for chunk in chunks] == [1, 3]
    assert [chunk.page_range for chunk in chunks] == [(1, 1), (3, 3)]
    assert isinstance(document_parser.parse_document(tmp_path / 'sample.pdf'), str)


def test_txt_page_metadata_is_absent(tmp_path):
    path = tmp_path / 'source.txt'
    path.write_text('plain text', encoding='utf-8')
    chunks = chunker.chunk_document(document_parser.parse_document_pages(path), path.name)
    assert chunks[0].text == 'plain text'
    assert chunks[0].page_number is None


def test_vector_debug_keeps_raw_candidates_and_score_semantics(caplog):
    class Collection:
        def query(self, **kwargs):
            return {'ids': [['a', 'b']], 'documents': [['A', 'B']],
                    'metadatas': [[{}, {}]], 'distances': [[0.2, 0.8]]}
    store = vector_store.VectorStore.__new__(vector_store.VectorStore)
    store.collection = Collection()
    found = store.query('private full question', top_k=2, similarity_threshold=0.5, query_embedding=[1.0])
    assert found[0]['vector_distance'] == 0.2
    assert found[0]['vector_similarity'] == pytest.approx(0.8)
    assert found[0]['vector_score'] == 0.2
    assert store.last_query_debug['raw_candidate_count'] == 2
    assert store.last_query_debug['filtered_count'] == 1
    assert store.last_query_debug['filtered_reasons'] == {'distance_threshold': 1}
    assert [c['chunk_id'] for c in store.last_query_debug['raw_candidates']] == ['a', 'b']
    assert 'private full question' not in caplog.text


@pytest.mark.parametrize('size, overlap', [(0, 0), (10, -1), (10, 10)])
def test_invalid_chunk_settings_rejected(size, overlap):
    with pytest.raises(ValueError):
        chunker.chunk_text('text', 'test.txt', size, overlap)


def test_single_newline_paragraphs_are_preferred_to_cutting_a_line():
    text = 'First line of context\nSecond complete line\nThird complete line\n'
    chunks = chunker.chunk_text(text, 'lines.txt', chunk_size=35, overlap=4)
    assert chunks[0].text == 'First line of context\n'
    assert chunks[1].text == 'Second complete line\n'
    assert_exact_coverage(text, chunks, 35)


def test_chinese_section_heading_keeps_following_list_items():
    text = '\u4e00\u3001\u7528\u6237\u7ba1\u7406\n- \u8d26\u53f7\u521b\u5efa\n- \u5bc6\u7801\u4fee\u6539\n\n\u4e8c\u3001\u6587\u6863\u7ba1\u7406\n\u6587\u6863\u4e0a\u4f20\u3002'
    chunks = chunker.chunk_text(text, 'guide.txt', 50, 5)
    assert len(chunks) == 2
    assert chunks[0].section_title == '\u4e00\u3001\u7528\u6237\u7ba1\u7406'
    assert chunks[1].section_title == '\u4e8c\u3001\u6587\u6863\u7ba1\u7406'
    assert_exact_coverage(text, chunks, 50)


def test_generic_uppercase_resume_headings_keep_short_section_together():
    text = ('PROFILE\nEngineer focused on reliable systems.\n\n'
            'EDUCATION BACKGROUND\nUniversity A - BSc Engineering\nUniversity B - MSc Systems\n\n'
            'WORK EXPERIENCE\nBuilt and tested a document retrieval tool.\n')
    chunks = chunker.chunk_text(text, 'resume.txt', chunk_size=110, overlap=10)
    education = [chunk for chunk in chunks if chunk.section_title == 'EDUCATION BACKGROUND']
    assert len(education) == 1
    assert 'University A' in education[0].text and 'University B' in education[0].text
    assert 'WORK EXPERIENCE' not in education[0].text
    assert len(chunks) == 3
    assert_exact_coverage(text, chunks, 110)


def test_uppercase_lists_numbers_and_long_sentences_do_not_create_sections():
    text = '# Existing\n- IMPORTANT ITEM\n2026\nTHIS IS A LONG UPPERCASE SENTENCE THAT SHOULD STAY BODY TEXT.\n'
    chunks = chunker.chunk_text(text, 'guide.txt', 200, 10)
    assert len(chunks) == 1
    assert chunks[0].section_title == 'Existing'
