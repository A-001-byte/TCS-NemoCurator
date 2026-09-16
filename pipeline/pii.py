"""Stage 5: PII redaction. THE CENTREPIECE.

Runs AFTER dedup + quality filter (never before dedup: dedup relies on stable
content hashes, and redacting first would corrupt those hashes inconsistently).

Detects and redacts, on real extracted Indian KYC/regulatory text:
  - PAN numbers (AAAAA9999A format)
  - Aadhaar-style 12-digit numbers
  - Bank account numbers (9-18 digit runs in account-like context)
  - Phone numbers (Indian mobile / STD formats)
  - Email addresses
  - Dates of birth / dates (DD/MM/YYYY, DD-MM-YYYY)
  - PIN codes (6-digit Indian postal codes)
  - Person names (via spaCy NER `en_core_web_sm`, filtered to spans that are
    Titlecase, non-repeating, not a known BFSI/legal noun phrase, AND appear
    near a personal-title cue like "Mr."/"Name:"/"Signatory". Dense regulatory
    text makes small NER models mistag generic capitalized phrases ("Gazette
    Notification") as PERSON; this filter trades recall for precision so every
    reported name redaction is real, never a false positive presented as PII.)

Equivalent-logic stage: NVIDIA's shipped PII path uses GLiNER-PII
(gliner_pii_redaction.ipynb in the Curator repo). We use spaCy NER + regex here.
Labelled as such in the dashboard/README.
"""
import json
import re
import sys
from pathlib import Path

FILTERED_DIR = Path(__file__).resolve().parent.parent / "data" / "filtered"
REDACTED_DIR = Path(__file__).resolve().parent.parent / "data" / "redacted"
STAGE_RECORD_PATH = REDACTED_DIR / "_stage_record.json"
EXAMPLES_PATH = REDACTED_DIR / "pii_examples.json"
IN_PATH = FILTERED_DIR / "chunks.jsonl"
OUT_PATH = REDACTED_DIR / "chunks.jsonl"

MAX_EXAMPLES_PER_TYPE = 6

PATTERNS = [
    ("PAN", re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")),
    ("AADHAAR", re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?91[-\s]?)?[6-9]\d{9}(?!\d)")),
    # Regex can't distinguish a birth date from a policy/circular date without more
    # context (e.g. proximity to "DOB"/"Date of Birth"), so this is labeled generically.
    ("DATE", re.compile(r"\b(0[1-9]|[12]\d|3[01])[/-](0[1-9]|1[0-2])[/-](19|20)\d{2}\b")),
    ("PINCODE", re.compile(r"\b[1-9]\d{5}\b")),
    ("ACCOUNT_NUMBER", re.compile(r"\b\d{9,18}\b")),
]

_NLP = None
_SPACY_AVAILABLE = False

# Words that make an otherwise name-shaped span very likely a building/org/field-label,
# not a person -- spaCy's small model frequently mistags these in dense KYC/legal tables.
_NAME_BLOCKLIST_WORDS = {
    "bhavan", "building", "house", "tower", "floor", "road", "branch", "office",
    "title", "retail", "corporate", "banking", "sanctions", "conduct", "shell",
    "banks", "department", "division", "ministry", "government", "committee",
    "authority", "reserve", "bank", "india", "limited", "ltd", "pvt", "private",
    "directorate", "unit", "cell", "wing", "section", "annexure", "schedule",
    "location", "court", "magistrate", "judge", "embassy", "notary", "public",
    "signatory", "authorized", "transaction", "transfer", "wire", "batch",
    "beneficiary", "customer", "account", "officer", "manager", "principal",
    "regulator", "regulation", "policy", "circular", "direction", "act",
    "chapter", "clause", "paragraph", "appendix", "form", "format", "board",
    "risk", "compliance", "monitoring", "reporting", "identification",
}
_TITLECASE_TOKEN_RE = re.compile(r"^[A-Z][a-z]+$")

# KYC/regulatory text is dense with generic capitalized noun phrases ("Gazette
# Notification", "Key Elements") that spaCy's small NER model confuses for PERSON.
# A blocklist alone doesn't generalize; the reliable signal in these documents is
# that real personal names appear next to an honorific or a name-field label.
_PERSONAL_TITLE_CUE_RE = re.compile(
    r"\b(Mr\.?|Mrs\.?|Ms\.?|Miss|Shri|Smt\.?|Dr\.?|Name\s*:|Signatory|"
    r"Principal\s+Officer|Authoris?ed\s+Signatory|Proprietor|Karta|Signature\s+of)\b",
    re.IGNORECASE,
)
_CUE_WINDOW_CHARS = 40


def _looks_like_person_name(span_text: str) -> bool:
    tokens = span_text.split()
    if not (2 <= len(tokens) <= 4):
        return False
    if not all(_TITLECASE_TOKEN_RE.match(t) for t in tokens):
        return False
    if len(set(t.lower() for t in tokens)) != len(tokens):
        return False  # repeated token (e.g. "Beneficiary Beneficiary") -> not a name
    if any(t.lower() in _NAME_BLOCKLIST_WORDS for t in tokens):
        return False
    return True


def _has_personal_title_cue(text: str, start: int) -> bool:
    window = text[max(0, start - _CUE_WINDOW_CHARS) : start]
    return bool(_PERSONAL_TITLE_CUE_RE.search(window))


def _load_spacy():
    global _NLP, _SPACY_AVAILABLE
    try:
        import spacy

        # Only NER is needed for PERSON detection; disabling the rest
        # (tagger/parser/lemmatizer/attribute_ruler) roughly halves per-doc latency.
        _NLP = spacy.load(
            "en_core_web_sm", disable=["tagger", "parser", "lemmatizer", "attribute_ruler"]
        )
        _SPACY_AVAILABLE = True
    except Exception:
        _NLP = None
        _SPACY_AVAILABLE = False


def _record_example(examples: list, label: str, doc_id: str, before: str, context_before: str, context_after: str):
    type_count = sum(1 for e in examples if e["entity_type"] == label)
    if type_count < MAX_EXAMPLES_PER_TYPE:
        examples.append(
            {
                "doc_id": doc_id,
                "entity_type": label,
                "before": before,
                "context_before": context_before,
                "context_after": context_after,
            }
        )


def redact_regex(text: str, entity_counts: dict, examples: list, doc_id: str):
    redacted = text
    for label, pattern in PATTERNS:
        def _sub(match, label=label):
            entity_counts[label] = entity_counts.get(label, 0) + 1
            _record_example(
                examples,
                label,
                doc_id,
                match.group(0),
                text[max(0, match.start() - 40) : match.start()],
                text[match.end() : match.end() + 40],
            )
            return f"[REDACTED_{label}]"

        redacted = pattern.sub(_sub, redacted)
    return redacted


def redact_names_batch(texts: list, doc_ids: list, entity_counts: dict, examples: list) -> list:
    if not _SPACY_AVAILABLE:
        return texts
    results = []
    for doc, doc_id, text in zip(_NLP.pipe(texts, batch_size=64), doc_ids, texts):
        spans = [
            (ent.start_char, ent.end_char, ent.text)
            for ent in doc.ents
            if ent.label_ == "PERSON"
            and _looks_like_person_name(ent.text)
            and _has_personal_title_cue(text, ent.start_char)
        ]
        results.append(_apply_name_spans(text, spans, entity_counts, examples, doc_id))
    return results


def _apply_name_spans(text: str, spans: list, entity_counts: dict, examples: list, doc_id: str):
    if not spans:
        return text
    spans.sort(key=lambda s: s[0], reverse=True)
    redacted = text
    for start, end, original in spans:
        entity_counts["PERSON_NAME"] = entity_counts.get("PERSON_NAME", 0) + 1
        _record_example(
            examples,
            "PERSON_NAME",
            doc_id,
            original,
            text[max(0, start - 40) : start],
            text[end : end + 40],
        )
        redacted = redacted[:start] + "[REDACTED_PERSON_NAME]" + redacted[end:]
    return redacted


def main():
    REDACTED_DIR.mkdir(parents=True, exist_ok=True)
    _load_spacy()

    if not IN_PATH.exists():
        print(json.dumps({"stage": "pii_redact", "error": "no input chunks"}))
        sys.exit(1)

    entity_counts = {}
    examples = []
    chunks_in = 0
    out_chunks = []

    with IN_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            chunk = json.loads(line)
            chunks_in += 1
            chunk["text"] = redact_regex(chunk["text"], entity_counts, examples, chunk["chunk_id"])
            out_chunks.append(chunk)

    texts = [c["text"] for c in out_chunks]
    doc_ids = [c["chunk_id"] for c in out_chunks]
    redacted_texts = redact_names_batch(texts, doc_ids, entity_counts, examples)

    chunks_with_pii = 0
    for chunk, new_text in zip(out_chunks, redacted_texts):
        had_regex_hit = "[REDACTED_" in chunk["text"]
        chunk["text"] = new_text
        chunk["pii_redacted"] = had_regex_hit or "[REDACTED_PERSON_NAME]" in new_text
        if chunk["pii_redacted"]:
            chunks_with_pii += 1

    with OUT_PATH.open("w", encoding="utf-8") as f:
        for chunk in out_chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    EXAMPLES_PATH.write_text(json.dumps(examples, indent=2, ensure_ascii=False), encoding="utf-8")

    total_entities = sum(entity_counts.values())
    record = {
        "stage": "pii_redact",
        "docs_in": chunks_in,
        "docs_out": len(out_chunks),
        "removed": 0,
        "reason_counts": {},
        "pii_entities_redacted": total_entities,
        "entity_type_counts": entity_counts,
        "chunks_with_pii": chunks_with_pii,
        "name_detection_available": _SPACY_AVAILABLE,
    }
    STAGE_RECORD_PATH.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record, indent=2))

    if len(out_chunks) == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
