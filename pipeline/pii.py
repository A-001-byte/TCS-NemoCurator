"""Stage 5: PII redaction. THE CENTREPIECE.

Runs AFTER dedup + quality filter (never before dedup: dedup relies on stable
content hashes, and redacting first would corrupt those hashes inconsistently).

Detects and redacts, on real extracted Indian KYC/regulatory text:
  - PAN numbers (AAAAA9999A format)
  - Aadhaar numbers (12 digits, first digit 2-9; Verhoeff checksum or an Aadhaar label required)
  - CIN, Corporate Identity Number (21-char MCA format, e.g. U65923UR1922PLC000234)
  - SWIFT/BIC codes (shape + required "SWIFT"/"BIC" cue, e.g. BARBINBBXXX)
  - Bank account numbers (9-18 digit runs, gated by cross-field context validation)
  - Phone numbers (Indian mobile / STD formats)
  - Email addresses
  - Dates of birth (DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY; only after a DOB cue, so public
    regulatory dates such as "circular dated 23-10-2018" are kept)
  - PIN codes (6-digit Indian postal codes; only with a PIN label or after a place name and
    hyphen/comma, never after a money word: "Urban 150000" is an amount, not an address)
  - Person names (via spaCy NER `en_core_web_sm`, filtered to spans that are
    Titlecase, non-repeating, not a known BFSI/legal noun phrase, AND appear
    near a personal-title cue like "Mr."/"Name:"/"Signatory". Dense regulatory
    text makes small NER models mistag generic capitalized phrases ("Gazette
    Notification") as PERSON; this filter trades recall for precision so every
    reported name redaction is real, never a false positive presented as PII.)
    Initials ("Shri R. K. Sharma") and ALL-CAPS names ("MR. SURESH KUMAR"), which spaCy
    misses, are also caught, but only directly after a title and never job titles.

Cross-field validation (Stream C): an account-number-shaped span is only redacted as
ACCOUNT_NUMBER once its SURROUNDING CONTEXT agrees. On the real 19-document corpus every
single 9-18 digit run the bare regex matched was actually a fax or telephone number from
a published RBI/MHA circular, not a bank account. Pattern-in-isolation cannot tell those
apart; pattern-plus-context can. See `_account_number_verdict`.

Document-level validation report (Stream C): alongside per-entity redaction, writes
`data/redacted/validation_report.json` -- one row per source document with entity counts
by type and how many chunks a human should re-check, ordered most-exposed first.

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
VALIDATION_REPORT_PATH = REDACTED_DIR / "validation_report.json"
IN_PATH = FILTERED_DIR / "chunks.jsonl"
OUT_PATH = REDACTED_DIR / "chunks.jsonl"

MAX_EXAMPLES_PER_TYPE = 6

PATTERNS = [
    ("PAN", re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")),
    # First digit 2-9; separators are space or hyphen only (never a newline). Candidates are
    # validated by Verhoeff checksum / cue words: see _aadhaar_verdict.
    ("AADHAAR", re.compile(r"\b[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}\b")),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?91[-\s]?)?[6-9]\d{9}(?!\d)")),
    # The shape also matches public regulatory dates ("circular dated 23-10-2018"), so a
    # match is only redacted when a date-of-birth cue precedes it: see _has_dob_cue.
    # Same separator on both sides: / - or . (RBI writes 18.11.2019).
    ("DATE", re.compile(r"\b(?:0?[1-9]|[12]\d|3[01])([/.-])(?:0?[1-9]|1[0-2])\1(?:19|20)\d{2}\b")),
    ("PINCODE", re.compile(r"\b[1-9]\d{5}\b")),
    # CIN: MCA Corporate Identity Number. Listed/Unlisted + 5-digit industry code +
    # 2-letter state + 4-digit year + 3-letter ownership + 6-digit registration number.
    # Runs before ACCOUNT_NUMBER so a CIN's digit runs are never mistaken for one.
    ("CIN", re.compile(r"\b[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}\b")),
    # SWIFT/BIC: 4-char bank + 2-char country + 2-char location + optional 3-char branch.
    # Shape alone is far too loose -- plain uppercase words ("ACCOUNTS", "ANNEXURE") match
    # it -- so a cue is REQUIRED before redacting. See _has_swift_cue.
    ("SWIFT_BIC", re.compile(r"\b[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b")),
    ("ACCOUNT_NUMBER", re.compile(r"\b\d{9,18}\b")),
]

# --- Cross-field validation for ACCOUNT_NUMBER -------------------------------
# A bare 9-18 digit run is the weakest pattern here: Indian landline+STD strings,
# fax numbers and concatenated helpline numbers all match it. Deciding by pattern
# alone mislabels published contact numbers as customer bank accounts.
ACCOUNT_CONTEXT_WINDOW = 90
TELECOM_CUE_RE = re.compile(
    r"(fax|tele\s?phone|phone|mobile|helpline|contact\s+(no|number)|\bM\s*:|\bTel\b|\bSTD\b)",
    re.IGNORECASE,
)
BANK_ACCOUNT_CUE_RE = re.compile(
    r"(a/c|account\s*(no|number|#)|bank\s+account|savings\s+account|current\s+account"
    r"|credited\s+to|debited\s+from|beneficiary\s+account|\bIFSC\b)",
    re.IGNORECASE,
)


def _account_number_verdict(text: str, start: int, end: int) -> str:
    """Decide what an account-number-shaped span actually is, from its neighbours.

    Returns 'suppress' (telecom context -> not an account number at all),
    'confident' (explicit bank-account context), or 'needs_review' (no context
    either way -> still redacted, but flagged so a human can check).
    """
    window = text[max(0, start - ACCOUNT_CONTEXT_WINDOW) : end + ACCOUNT_CONTEXT_WINDOW]
    if TELECOM_CUE_RE.search(window):
        return "suppress"
    if BANK_ACCOUNT_CUE_RE.search(window):
        return "confident"
    return "needs_review"


# --- Cue requirement for SWIFT_BIC -------------------------------------------
# Same precision-first discipline as PERSON_NAME: the shape is too permissive on its
# own (any 8-letter uppercase word matches), so an explicit label must precede it.
# Case-sensitive on purpose -- lowercase "swiftly" is ordinary prose, and \bBIC\b
# keeps "CBIC" (Central Board of Indirect Taxes and Customs) from qualifying.
SWIFT_CUE_WINDOW = 60
SWIFT_CUE_RE = re.compile(r"(SWIFT\s*(Address|Code|BIC)?|\bBIC\b)")


def _has_swift_cue(text: str, start: int) -> bool:
    return bool(SWIFT_CUE_RE.search(text[max(0, start - SWIFT_CUE_WINDOW) : start]))


# --- Cue requirement for DATE -------------------------------------------------
# A birth date is personal data; "circular dated 23-10-2018" is public regulatory
# history that a compliance corpus must keep. Only a date-of-birth cue shortly BEFORE
# the date (same line) marks it as personal.
DOB_CUE_WINDOW = 30
DOB_CUE_RE = re.compile(r"(?:\bD\.?\s?O\.?\s?B\b|date\s+of\s+birth|\bborn\b)", re.IGNORECASE)


def _has_dob_cue(text: str, start: int) -> bool:
    window = text[max(0, start - DOB_CUE_WINDOW) : start].rsplit("\n", 1)[-1]
    return bool(DOB_CUE_RE.search(window))


# --- Context validation for PINCODE -------------------------------------------
# Any 6-digit number matches the shape: money amounts ("Urban 150000"), the tail of a
# phone number ("05942-233739"). A PIN code is accepted only with a PIN label right before
# it, or when it directly follows a place name and a hyphen/comma ("Mumbai-400001").
# Indian PIN prefixes run 11..99; a number right after a money word is an amount.
# NOTE: office addresses in public regulatory documents are institutional, not personal
# data; they are still redacted (cheap and safe) but described as "address PIN codes".
PIN_CONTEXT_WINDOW = 25
PIN_LABEL_RE = re.compile(r"\bpin[\s-]?(?:code)?(?:\s*(?:no\.?|number))?\s*[:#.\-–—]*\s*$", re.IGNORECASE)
PIN_AFTER_PLACE_RE = re.compile(r"[A-Za-z]{3,}\s*[-,–—]\s*$")
PIN_MONEY_CUE_RE = re.compile(
    r"(?:\bRs\.?|\bINR|₹|\bamount|\babove|\bexceeding|\bthreshold|\bof)\s*[:.\-–]?\s*$",
    re.IGNORECASE,
)
MIN_PIN_PREFIX = 11


def _pincode_verdict(text: str, start: int, end: int) -> str:
    """'accept', 'reject_no_cue', or 'reject_other' (money cue / impossible prefix)."""
    if int(text[start : start + 2]) < MIN_PIN_PREFIX:
        return "reject_other"
    before = text[max(0, start - PIN_CONTEXT_WINDOW) : start]
    if PIN_MONEY_CUE_RE.search(before):
        return "reject_other"
    if PIN_LABEL_RE.search(before) or PIN_AFTER_PLACE_RE.search(before):
        return "accept"
    return "reject_no_cue"


# --- Verification for AADHAAR -------------------------------------------------
# Real Aadhaar numbers carry a Verhoeff check digit. Checksum-valid -> redact. Invalid
# but an Aadhaar label nearby -> still redact, flagged for review (typo or OCR error).
# Otherwise it is just a digit run (a reference number, a table value).
_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9), (1, 2, 3, 4, 0, 6, 7, 8, 9, 5), (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7), (4, 0, 1, 2, 3, 9, 5, 6, 7, 8), (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2), (7, 6, 5, 9, 8, 2, 1, 0, 4, 3), (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9), (1, 5, 7, 6, 2, 8, 3, 0, 9, 4), (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7), (9, 4, 5, 3, 1, 2, 6, 8, 7, 0), (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5), (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)
AADHAAR_CUE_WINDOW = 60
AADHAAR_CUE_RE = re.compile(r"(?:aadhaar|aadhar|\bUID\b|UIDAI)", re.IGNORECASE)


def verhoeff_valid(digits: str) -> bool:
    """True if the digit string (check digit last) passes the Verhoeff checksum."""
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][int(ch)]]
    return c == 0


def _aadhaar_verdict(text: str, start: int, end: int) -> str:
    """'valid' (checksum passes), 'needs_review' (checksum fails, Aadhaar label nearby),
    or 'reject' (neither: not treated as an Aadhaar number)."""
    digits = re.sub(r"\D", "", text[start:end])
    if verhoeff_valid(digits):
        return "valid"
    window = text[max(0, start - AADHAAR_CUE_WINDOW) : end + AADHAAR_CUE_WINDOW]
    return "needs_review" if AADHAAR_CUE_RE.search(window) else "reject"


# --- Document-level validation report ----------------------------------------
# Per-entity redaction answers "what was hidden"; a compliance reviewer also needs
# "which documents carried the most exposure, and where should a human look first".
# Counted from the placeholders left in the final text: each redaction writes exactly
# one, so this stays correct without threading extra state through the redaction loop.
REDACTION_PLACEHOLDER_RE = re.compile(r"\[REDACTED_([A-Z_]+)\]")


def build_validation_report(chunks: list) -> list:
    """Per-document PII summary, ordered most-exposed first."""
    docs = {}
    for chunk in chunks:
        doc = docs.setdefault(
            chunk["doc_id"],
            {
                "doc_id": chunk["doc_id"],
                "source_file": chunk["source_file"],
                "chunks": 0,
                "chunks_with_pii": 0,
                "chunks_flagged_for_review": 0,
                "pii_entities": 0,
                "entity_types": {},
            },
        )
        doc["chunks"] += 1
        if chunk.get("pii_redacted"):
            doc["chunks_with_pii"] += 1
        if chunk.get("validation_flag") == "needs_review":
            doc["chunks_flagged_for_review"] += 1
        for entity_type in REDACTION_PLACEHOLDER_RE.findall(chunk["text"]):
            doc["entity_types"][entity_type] = doc["entity_types"].get(entity_type, 0) + 1
            doc["pii_entities"] += 1

    report = []
    for doc in docs.values():
        doc["distinct_entity_types"] = len(doc["entity_types"])
        report.append(doc)
    report.sort(key=lambda d: (-d["pii_entities"], d["doc_id"]))
    return report


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


# --- PERSON_NAME recall: initials and ALL-CAPS, only after a title ----------------
# spaCy's small model misses "Shri R. K. Sharma" and "MR. SURESH KUMAR". A name is accepted
# here only right after Shri/Smt/Mr/Mrs/Ms/Dr, and only in the two shapes spaCy misses:
# initials + surname, or 2+ ALL-CAPS words. Job titles and common words never qualify, so
# "Mr. Managing Director" and "DR. NOTE THAT" stay untouched. Plain Title-Case names after
# a title ("Mr. Pankaj Mittal") remain the spaCy path's job.
_TITLE_START_RE = re.compile(r"\b(?:(?:Shri|Smt|Mr|Mrs|Ms|Dr)\.?|(?:SHRI|SMT)\.?|(?:MR|MRS|MS|DR)\.)[ \t]+")
_MAX_NAME_TOKENS = 5
_INITIAL_RE = re.compile(r"[A-Z]\.")
_CAPS_RE = re.compile(r"[A-Z]{2,}")
_WORD_NAME_RE = re.compile(r"[A-Z][a-z]+")
_JOB_TITLE_WORDS = {
    "managing", "director", "joint", "secretary", "chairman", "chairperson", "chief",
    "executive", "general", "deputy", "assistant", "senior", "vice", "president", "head",
    "governor", "additional", "special", "under", "nodal", "designated",
}
_COMMON_WORDS = {
    "the", "and", "for", "that", "this", "note", "see", "not", "are", "all", "any", "with",
    "from", "shall", "should", "may", "must", "will", "also", "only", "each", "such",
    "their", "these", "none", "nil", "yes", "no",
}
_NOT_A_NAME = _NAME_BLOCKLIST_WORDS | _JOB_TITLE_WORDS | _COMMON_WORDS


def _title_gated_names(text: str) -> list:
    """(start, end, text) for initials/ALL-CAPS names that directly follow a title."""
    spans = []
    for title in _TITLE_START_RE.finditer(text):
        pos, tokens, end = title.end(), [], title.end()
        while len(tokens) < _MAX_NAME_TOKENS:
            match = re.compile(r"\S+").match(text, pos)
            if not match:
                break
            raw, trailing = match.group(0), ""
            if raw[-1] in ",;:":
                raw, trailing = raw[:-1], raw[-1]
            if raw.endswith(".") and not _INITIAL_RE.fullmatch(raw):
                raw, trailing = raw[:-1], "."
            if _INITIAL_RE.fullmatch(raw):
                kind = "initial"
            elif _CAPS_RE.fullmatch(raw):
                kind = "caps"
            elif _WORD_NAME_RE.fullmatch(raw):
                kind = "word"
            else:
                break
            tokens.append((kind, raw))
            end = match.start() + len(raw)
            gap = re.compile(r"[ \t]+").match(text, match.end())
            if trailing or not gap:
                break
            pos = gap.end()
        kinds = [k for k, _ in tokens]
        has_initial = "initial" in kinds
        initials_plus_surname = has_initial and any(k != "initial" for k in kinds)
        all_caps_name = len(tokens) >= 2 and all(k == "caps" for k in kinds)
        if (initials_plus_surname or all_caps_name) and not any(
            word.lower().rstrip(".") in _NOT_A_NAME for _, word in tokens
        ):
            start = title.end()
            spans.append((start, end, text[start:end]))
    return spans


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


def redact_regex(text: str, entity_counts: dict, examples: list, doc_id: str, validation: dict):
    redacted = text
    for label, pattern in PATTERNS:
        def _sub(match, label=label):
            # match.string is the text actually being scanned this pass, so context
            # windows stay correct even after earlier patterns changed span lengths.
            scanned = match.string
            context_before = scanned[max(0, match.start() - 40) : match.start()]
            context_after = scanned[match.end() : match.end() + 40]

            if label == "ACCOUNT_NUMBER":
                verdict = _account_number_verdict(scanned, match.start(), match.end())
                if verdict == "suppress":
                    validation["account_suppressed"] = validation.get("account_suppressed", 0) + 1
                    _record_example(
                        examples,
                        "ACCOUNT_NUMBER_SUPPRESSED",
                        doc_id,
                        match.group(0),
                        context_before,
                        context_after,
                    )
                    return match.group(0)
                if verdict == "needs_review":
                    validation["account_needs_review"] = (
                        validation.get("account_needs_review", 0) + 1
                    )

            elif label == "SWIFT_BIC" and not _has_swift_cue(scanned, match.start()):
                validation["swift_no_cue"] = validation.get("swift_no_cue", 0) + 1
                return match.group(0)

            elif label == "DATE" and not _has_dob_cue(scanned, match.start()):
                validation["date_no_cue"] = validation.get("date_no_cue", 0) + 1
                return match.group(0)

            elif label == "PINCODE":
                verdict = _pincode_verdict(scanned, match.start(), match.end())
                if verdict != "accept":
                    key = "pincode_no_cue" if verdict == "reject_no_cue" else "pincode_other"
                    validation[key] = validation.get(key, 0) + 1
                    return match.group(0)

            elif label == "AADHAAR":
                verdict = _aadhaar_verdict(scanned, match.start(), match.end())
                if verdict == "reject":
                    validation["aadhaar_rejected"] = validation.get("aadhaar_rejected", 0) + 1
                    return match.group(0)
                if verdict == "needs_review":
                    validation["aadhaar_needs_review"] = validation.get("aadhaar_needs_review", 0) + 1

            entity_counts[label] = entity_counts.get(label, 0) + 1
            _record_example(examples, label, doc_id, match.group(0), context_before, context_after)
            return f"[REDACTED_{label}]"

        redacted = pattern.sub(_sub, redacted)
    return redacted


def redact_names_batch(texts: list, doc_ids: list, entity_counts: dict, examples: list) -> list:
    if _SPACY_AVAILABLE:
        spacy_spans = [
            [
                (ent.start_char, ent.end_char, ent.text)
                for ent in doc.ents
                if ent.label_ == "PERSON"
                and _looks_like_person_name(ent.text)
                and _has_personal_title_cue(text, ent.start_char)
            ]
            for doc, text in zip(_NLP.pipe(texts, batch_size=64), texts)
        ]
    else:
        spacy_spans = [[] for _ in texts]
    results = []
    for text, doc_id, spans in zip(texts, doc_ids, spacy_spans):
        # initials / ALL-CAPS names after a title; skip any span spaCy already found
        extra = [
            s for s in _title_gated_names(text)
            if not any(s[0] < end and start < s[1] for start, end, _ in spans)
        ]
        results.append(_apply_name_spans(text, spans + extra, entity_counts, examples, doc_id))
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


# ---------------------------------------------------------------------------
# STREAM A — Real GLiNER-PII (nvidia/gliner-PII)
#
# Zero-shot NER, single pass finds all entity types at once. CPU-friendly,
# confirmed via model card (no GPU-only restriction like the quality
# classifier had). Runs independently of Stream C's regex+cross-field-
# validation pipeline below -- does NOT replicate C's telecom-vs-bank-account
# or SWIFT-cue disambiguation logic. That's a known, deliberate gap to
# report on, not a bug to silently patch.
# ---------------------------------------------------------------------------

USE_GLINER_PII = False  # flip True to use real GLiNER instead of regex+spaCy+validation

_gliner_model = None

# Covers every entity type currently in PATTERNS + spaCy PERSON, including
# Stream C's CIN and SWIFT_BIC additions.
GLINER_LABEL_MAP = {
    "person": "PERSON_NAME",
    "email address": "EMAIL",
    "phone number": "PHONE",
    "date of birth": "DATE",
    "pan card number": "PAN",
    "aadhaar number": "AADHAAR",
    "pin code": "PINCODE",
    "bank account number": "ACCOUNT_NUMBER",
    "corporate identity number": "CIN",
    "swift code": "SWIFT_BIC",
}
GLINER_LABELS = list(GLINER_LABEL_MAP.keys())
GLINER_CONFIDENCE_THRESHOLD = 0.3  # NVIDIA's own eval used this threshold

# GLiNER's encoder has a ~384 subword-token limit; predict_entities silently
# stops finding anything past that on a single unwindowed call rather than
# erroring, so long chunks would quietly lose PII coverage. Window by word
# count (conservative proxy for subword tokens) with overlap so an entity
# straddling a window boundary is still caught in at least one window.
GLINER_MAX_WINDOW_WORDS = 220
GLINER_WINDOW_OVERLAP_WORDS = 30
_WORD_RE = re.compile(r"\S+")


def _gliner_windows(text: str) -> list:
    """Split into overlapping (window_text, char_offset) pairs, each under
    GLINER_MAX_WINDOW_WORDS words, so span offsets can be translated back to
    the original text. Returns [(text, 0)] unchanged if already short enough.
    """
    words = list(_WORD_RE.finditer(text))
    if len(words) <= GLINER_MAX_WINDOW_WORDS:
        return [(text, 0)]
    step = GLINER_MAX_WINDOW_WORDS - GLINER_WINDOW_OVERLAP_WORDS
    windows = []
    i = 0
    while i < len(words):
        group = words[i : i + GLINER_MAX_WINDOW_WORDS]
        start, end = group[0].start(), group[-1].end()
        windows.append((text[start:end], start))
        if i + GLINER_MAX_WINDOW_WORDS >= len(words):
            break
        i += step
    return windows


# Per docs/A1_2_pii_gliner_comparison.md: GLiNER fires PERSON on job titles ("Managing
# Director", "Joint Secretary"); PHONE/EMAIL looked good. With the guard on, a GLiNER PERSON
# span is kept only if it passes the same title-cue + name-shape test as the spaCy path.
GLINER_PERSON_GUARD = True
# None = redact every GLiNER type; or a set such as {"PHONE", "EMAIL"} to restrict it.
GLINER_ENABLED_TYPES = None


def _load_gliner():
    global _gliner_model
    if _gliner_model is not None:
        return
    try:
        from gliner import GLiNER  # lazy: gliner lives in the separate venv-pii, not the core env
    except ImportError as exc:
        raise RuntimeError(
            "USE_GLINER_PII is True but the 'gliner' package is not installed. Install it in "
            "the PII environment (see SETUP.md, venv-pii) or set USE_GLINER_PII = False."
        ) from exc
    _gliner_model = GLiNER.from_pretrained("nvidia/gliner-PII")


def _resolve_overlaps(spans: list) -> list:
    """Drop overlapping spans, keeping the higher-score one (then the longer, then the
    earlier). Returns the survivors ordered by start. A span is a dict with start/end/score."""
    ranked = sorted(spans, key=lambda s: (-s.get("score", 0.0), -(s["end"] - s["start"]), s["start"]))
    kept = []
    for span in ranked:
        if all(span["end"] <= k["start"] or span["start"] >= k["end"] for k in kept):
            kept.append(span)
    return sorted(kept, key=lambda s: s["start"])


def redact_pii_gliner(text: str, entity_counts: dict, examples: list, doc_id: str):
    """
    Real GLiNER-PII redaction for one chunk. Returns (redacted_text, had_pii: bool).
    Does not apply the regex path's cross-field validation (telecom-vs-account, SWIFT
    cue, DATE/PIN gates): GLiNER's own judgment, so a comparison shows what the model
    does alone. The one guard kept is GLINER_PERSON_GUARD (see above).

    Long chunks are run through _gliner_windows() and results are translated back to
    absolute offsets in `text`. Spans are then filtered, overlaps resolved
    (_resolve_overlaps), and replacements applied from the end of the text so earlier
    offsets stay valid.
    """
    _load_gliner()

    spans = []
    for window_text, offset in _gliner_windows(text):
        for ent in _gliner_model.predict_entities(
            window_text, GLINER_LABELS, threshold=GLINER_CONFIDENCE_THRESHOLD
        ):
            label = GLINER_LABEL_MAP.get(ent["label"], ent["label"].upper().replace(" ", "_"))
            span = {
                "label": label,
                "text": ent["text"],
                "start": ent["start"] + offset,
                "end": ent["end"] + offset,
                "score": ent.get("score", 0.0),
            }
            if GLINER_ENABLED_TYPES is not None and label not in GLINER_ENABLED_TYPES:
                continue
            if (
                label == "PERSON_NAME"
                and GLINER_PERSON_GUARD
                and not (_looks_like_person_name(span["text"]) and _has_personal_title_cue(text, span["start"]))
            ):
                continue
            spans.append(span)

    resolved = _resolve_overlaps(spans)
    redacted = text
    for span in reversed(resolved):
        entity_counts[span["label"]] = entity_counts.get(span["label"], 0) + 1
        _record_example(
            examples, span["label"], doc_id, span["text"],
            text[max(0, span["start"] - 40):span["start"]],
            text[span["end"]:span["end"] + 40],
        )
        redacted = redacted[:span["start"]] + f"[REDACTED_{span['label']}]" + redacted[span["end"]:]
    return redacted, bool(resolved)


def main():
    REDACTED_DIR.mkdir(parents=True, exist_ok=True)
    if USE_GLINER_PII:
        _load_gliner()  # fail now, with a clear message, if gliner is not installed
    else:
        _load_spacy()

    if not IN_PATH.exists():
        print(json.dumps({"stage": "pii_redact", "error": "no input chunks"}))
        sys.exit(1)

    entity_counts = {}
    examples = []
    validation_totals = {}
    chunks_in = 0
    out_chunks = []

    with IN_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            chunk = json.loads(line)
            chunks_in += 1
            chunk_validation = {}
            if USE_GLINER_PII:
                chunk["text"], _ = redact_pii_gliner(
                    chunk["text"], entity_counts, examples, chunk["chunk_id"]
                )
            else:
                chunk["text"] = redact_regex(
                    chunk["text"], entity_counts, examples, chunk["chunk_id"], chunk_validation
                )
            # Additive field per the frozen chunk contract: "needs_review" means PII was
            # redacted but its surrounding context didn't confirm the entity type.
            needs_review = chunk_validation.get("account_needs_review") or chunk_validation.get(
                "aadhaar_needs_review"
            )
            chunk["validation_flag"] = "needs_review" if needs_review else "confident"
            for key, count in chunk_validation.items():
                validation_totals[key] = validation_totals.get(key, 0) + count
            out_chunks.append(chunk)

    texts = [c["text"] for c in out_chunks]
    doc_ids = [c["chunk_id"] for c in out_chunks]
    # GLiNER already covers names (behind GLINER_PERSON_GUARD); the spaCy pass is the regex path's.
    redacted_texts = texts if USE_GLINER_PII else redact_names_batch(texts, doc_ids, entity_counts, examples)

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

    validation_report = build_validation_report(out_chunks)
    VALIDATION_REPORT_PATH.write_text(
        json.dumps(validation_report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

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
        "name_detection_available": USE_GLINER_PII or _SPACY_AVAILABLE,
        "pii_engine": "gliner" if USE_GLINER_PII else "regex+spacy",
        # Cross-field validation outcomes (Stream C)
        "account_numbers_suppressed": validation_totals.get("account_suppressed", 0),
        "account_numbers_needs_review": validation_totals.get("account_needs_review", 0),
        "swift_candidates_rejected_no_cue": validation_totals.get("swift_no_cue", 0),
        "date_candidates_rejected_no_cue": validation_totals.get("date_no_cue", 0),
        "pincode_candidates_rejected_no_cue": validation_totals.get("pincode_no_cue", 0),
        "pincode_candidates_rejected_money_or_prefix": validation_totals.get("pincode_other", 0),
        "aadhaar_candidates_rejected": validation_totals.get("aadhaar_rejected", 0),
        "aadhaar_needs_review": validation_totals.get("aadhaar_needs_review", 0),
        "documents_with_pii": sum(1 for d in validation_report if d["pii_entities"]),
        "validation_report_path": VALIDATION_REPORT_PATH.relative_to(REDACTED_DIR.parent.parent).as_posix(),
        "chunks_needing_review": sum(
            1 for c in out_chunks if c.get("validation_flag") == "needs_review"
        ),
    }
    STAGE_RECORD_PATH.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record, indent=2))

    if len(out_chunks) == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
