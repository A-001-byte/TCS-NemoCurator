"""Page numbers on chunks: finding where a chunk came from in the PDF, and carrying that into the output."""

import json
import shutil
from pathlib import Path

import pdfplumber
import pytest

from pipeline import dedup, extract, pages, run
from pipeline.api import curate

SAMPLE = "bank_of_baroda_kyc.pdf"


def make_pages(count: int = 4, words: int = 100) -> list:
    """Pages of distinct words: page n holds p<n>w0 ... p<n>w<words-1>."""
    return [" ".join(f"p{n}w{j}" for j in range(words)) for n in range(1, count + 1)]


def words_of(page_list: list, first: int, last: int) -> str:
    """Words `first` to `last` (inclusive) of the whole document, counting across pages."""
    return " ".join(" ".join(page_list).split()[first : last + 1])


@pytest.fixture
def index():
    return pages.PageIndex(make_pages())


def test_a_chunk_inside_one_page_gets_that_page(index):
    chunk = words_of(make_pages(), 210, 250)  # page 3 (words 200-299)
    assert index.locate(chunk)[:2] == (3, 3)


def test_a_chunk_across_a_page_break_gets_both_pages(index):
    chunk = words_of(make_pages(), 80, 140)  # page 1 into page 2
    assert index.locate(chunk)[:2] == (1, 2)


def test_a_chunk_missing_its_first_words_is_still_found(index):
    # healing removed a page header and repaired a word: the first run no longer matches
    chunk = "REPAIRED p2w5x " + words_of(make_pages(), 108, 160)
    assert index.locate(chunk)[:2] == (2, 2)


def test_punctuation_and_case_do_not_matter(index):
    chunk = ", ".join(w.upper() for w in words_of(make_pages(), 300, 340).split())
    assert index.locate(chunk)[:2] == (4, 4)


def test_text_that_is_not_in_the_document_gets_no_page(index):
    assert index.locate("these words never appear anywhere in the pages at all ever") is None


def test_a_chunk_too_short_to_match_gets_no_page(index):
    assert index.locate("p1w1 p1w2") is None
    assert pages.PageIndex([]).locate("anything at all here once more") is None


def test_a_repeated_clause_resolves_to_the_copy_after_the_cursor():
    clause = "the reporting entity shall maintain records for five years from the date of the transaction"
    texts = [
        f"{clause} first",
        "something else entirely here in the middle",
        "more filler words go here to fill",
        f"{clause} fourth",
    ]
    idx = pages.PageIndex(texts)
    assert idx.locate(clause)[0] == 1
    assert idx.locate(clause, cursor=len(pages.tokens(" ".join(texts[:3]))))[0] == 4


def test_the_last_page_is_never_before_the_first(index):
    first, last, _ = index.locate(words_of(make_pages(), 95, 130))
    assert first <= last


def test_chunks_without_kept_pages_get_none(tmp_path, monkeypatch):
    monkeypatch.setattr(dedup, "EXTRACTED_DIR", tmp_path)
    text = " ".join(f"word{i}" for i in range(400))
    chunks = dedup.build_chunks([{"doc_id": "d", "source_file": "d.pdf", "text": text}])
    assert chunks and all(c["page_start"] is None and c["page_end"] is None for c in chunks)


def test_extract_keeps_the_text_of_every_page(tmp_path, monkeypatch):
    raw, extracted = tmp_path / "raw", tmp_path / "extracted"
    raw.mkdir()
    shutil.copy(run.ROOT / "data" / "raw" / SAMPLE, raw / SAMPLE)
    monkeypatch.setattr(extract, "RAW_DIR", raw)
    monkeypatch.setattr(extract, "EXTRACTED_DIR", extracted)
    monkeypatch.setattr(extract, "STAGE_RECORD_PATH", extracted / "_stage_record.json")
    extract.main()
    kept = json.loads((extracted / (Path(SAMPLE).stem + extract.PAGES_SUFFIX)).read_text(encoding="utf-8"))["pages"]
    with pdfplumber.open(raw / SAMPLE) as pdf:
        assert len(kept) == len(pdf.pages)
    assert "\n".join(kept) == (extracted / (Path(SAMPLE).stem + ".txt")).read_text(encoding="utf-8")


def test_a_real_pdf_gets_page_numbers_in_the_output(tmp_path):
    inputs = tmp_path / "in"
    inputs.mkdir()
    shutil.copy(run.ROOT / "data" / "raw" / SAMPLE, inputs / SAMPLE)
    curate(inputs, tmp_path / "out", device="cpu")
    lines = (tmp_path / "out" / "curated.jsonl").read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line)["metadata"] for line in lines]
    with pdfplumber.open(inputs / SAMPLE) as pdf:
        total = len(pdf.pages)

    assert rows and all("page_start" in m and "page_end" in m for m in rows)
    assert all(m["page_start"] is not None for m in rows), "every chunk of this PDF should be located"
    assert all(1 <= m["page_start"] <= m["page_end"] <= total for m in rows)
    assert [m["page_start"] for m in rows] == sorted(m["page_start"] for m in rows), "chunks stay in page order"
    assert rows[0]["page_start"] == 1
    assert rows[-1]["page_end"] >= total - 1, "the last chunk is at or near the last page"
