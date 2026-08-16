from ingest.chunking import (
    clean_text,
    split_paragraphs,
    chunk_by_paragraphs,
    chunk_sliding_window,
    normalize_to_pages,
    build_chunks,
)


def test_clean_text_removes_excess_whitespace():
    assert clean_text("a   b\t\tc") == "a b c"


def test_clean_text_normalizes_newlines():
    assert clean_text("a\rb") == "a\nb"


def test_clean_text_collapses_many_blank_lines():
    assert "\n\n\n\n" not in clean_text("a\n\n\n\n\nb")


def test_split_paragraphs_splits_on_blank_lines():
    text = "first paragraph\n\nthe second paragraph"
    assert split_paragraphs(text) == ["first paragraph", "the second paragraph"]


def test_split_paragraphs_returns_empty_list_for_empty_input():
    assert split_paragraphs("") == []


def test_split_paragraphs_drops_stray_whitespace():
    parts = split_paragraphs("p1\n\ntext here\n   ")
    assert parts == ["p1", "text here"]


def test_chunk_by_paragraphs_keeps_short_text_whole():
    text = "This is a short piece of text that fits in a single chunk."
    chunks = chunk_by_paragraphs(text)
    assert len(chunks) == 1
    assert text in chunks[0]


def test_chunk_by_paragraphs_splits_page_larger_than_target():
    text = "word " * 400
    chunks = chunk_by_paragraphs(text, target_chars=200, overlap_chars=0)
    assert len(chunks) > 1


def test_chunk_by_paragraphs_applies_overlap_between_chunks():
    text = "word " * 300
    chunks = chunk_by_paragraphs(text, target_chars=150, overlap_chars=50)
    assert len(chunks) > 1
    assert chunks[0][-20:] in chunks[1]


def test_chunk_sliding_window_respects_target_and_step():
    text = "x" * 500
    chunks = chunk_sliding_window(text, target_chars=100, overlap_chars=25)
    assert all(len(c) <= 100 for c in chunks)
    assert len(chunks) > 1


def test_normalize_to_pages_groups_records_by_page():
    records = [
        {"doc": "a.pdf", "page": 1, "text": "one", "source": "unstructured", "type": "Title"},
        {"doc": "a.pdf", "page": 1, "text": "two", "source": "unstructured", "type": "NarrativeText"},
        {"doc": "a.pdf", "page": 2, "text": "three", "source": "unstructured", "type": "NarrativeText"},
    ]
    pages = normalize_to_pages(records)
    assert len(pages) == 2
    page_one = pages[0]
    assert page_one["page"] == 1
    assert "one" in page_one["text"] and "two" in page_one["text"]


def test_normalize_to_pages_sorts_by_page_number():
    records = [
        {"doc": "a.pdf", "page": 2, "text": "two", "source": "u", "type": "T"},
        {"doc": "a.pdf", "page": 1, "text": "one", "source": "u", "type": "T"},
    ]
    pages = normalize_to_pages(records)
    assert [p["page"] for p in pages] == [1, 2]


def test_build_chunks_produces_expected_schema():
    pages = [
        {
            "doc": "example.pdf",
            "page": 1,
            "text": "A short page followed by " + "words " * 30,
            "lang": "en",
            "source": "test",
            "types": ["PageText"],
        }
    ]
    chunks = build_chunks(pages, target_chars=120, overlap_chars=0)
    assert chunks
    required = {"chunk_id", "doc", "page", "chunk_index", "lang", "source", "types", "text", "char_len"}
    for chunk in chunks:
        assert required <= set(chunk.keys())