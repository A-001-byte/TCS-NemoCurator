"""Which version of a policy is newest, for ordering documents newest-first.

Dedup keeps the first copy of a chunk it sees, so documents must be visited newest
first: for regulation the version in force should survive, not the oldest.

Year source, in priority order:
  1. the filename / doc_id: a financial-year pair such as ``2024_25`` (-> 2025) or a
     plain year such as ``2021`` or ``aug2025``;
  2. the latest year the text mentions (``version_year``);
  3. 0.

Caveat: ``version_year`` takes the MAX year in the text, so a document that cites a
future deadline ("by 2027") would be mis-ordered. That is why the filename wins.
"""
import re

YEAR_RE = re.compile(r"\b(20[0-3]\d)\b")
FY_PAIR_RE = re.compile(r"(?<!\d)(20\d{2})_(\d{2})(?!\d)")
FILENAME_YEAR_RE = re.compile(r"(?<!\d)(20[0-3]\d)(?!\d)")


def version_year(text: str) -> int:
    """Latest year a document mentions -- a document can't cite what came after it."""
    years = [int(y) for y in YEAR_RE.findall(text)]
    return max(years) if years else 0


def filename_year(doc_id: str) -> int:
    """Year encoded in a filename/doc_id, or 0. A pair like 2024_25 means FY 2024-25."""
    years = []
    for start, end in FY_PAIR_RE.findall(doc_id):
        start, end = int(start), int(end)
        # a real financial-year pair ends the year after it starts (2024_25)
        years.append(start + 1 if end == (start + 1) % 100 else start)
    # plain years elsewhere in the name; the digits of a pair were already counted above
    years += [int(y) for y in FILENAME_YEAR_RE.findall(FY_PAIR_RE.sub(" ", doc_id))]
    return max(years) if years else 0


def document_year(doc_id: str, text: str) -> int:
    return filename_year(doc_id) or version_year(text)


def newest_first(records: list) -> list:
    """Document records ordered newest version first; ties broken by doc_id (deterministic)."""
    return sorted(records, key=lambda r: (-document_year(r["doc_id"], r["text"]), r["doc_id"]))
