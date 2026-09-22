"""Self-check for Stream C additions: CIN detection + account-number cross-field validation.

Run: python -m pipeline.test_pii_validation
Strings below are real spans from the corpus (public RBI/MHA circulars and bank policy
PDFs), plus synthetic account-context cases the corpus does not contain.
"""
from pipeline.pii import (
    PATTERNS,
    _account_number_verdict,
    _has_swift_cue,
    build_validation_report,
)

CIN_RE = dict(PATTERNS)["CIN"]
ACCOUNT_RE = dict(PATTERNS)["ACCOUNT_NUMBER"]
SWIFT_RE = dict(PATTERNS)["SWIFT_BIC"]


def _swift_accepted(text: str) -> bool:
    """True if the first SWIFT-shaped span in `text` would actually be redacted."""
    match = SWIFT_RE.search(text)
    return bool(match) and _has_swift_cue(text, match.start())


def _verdict(text: str) -> str:
    match = ACCOUNT_RE.search(text)
    assert match, f"no account-shaped span in {text!r}"
    return _account_number_verdict(text, match.start(), match.end())


def main():
    # CIN: both real corpus values match, near-misses do not.
    assert CIN_RE.search("CIN No. U65923UR1922PLC000234, website")
    assert CIN_RE.search("Corporate Identity Number or CIN : U74140WB1983PTC036093)")
    assert not CIN_RE.search("U65923UR1922PLC00023")     # 5 trailing digits, not 6
    assert not CIN_RE.search("X65923UR1922PLC000234")    # must start L or U
    assert not CIN_RE.search("400001 Mumbai 9820320181")  # pincode + mobile, not a CIN

    # Telecom context -> not an account number (every real corpus hit is this case).
    assert _verdict("Nodal Officer for the UAPA at Fax No. 011-230923465 and also") == "suppress"
    assert _verdict("[Telephone Number: 011-23092548, 01123092551 (Fax), email") == "suppress"
    assert _verdict("Risk Consulting M: +91 9820320181 M: +(91) 8130166550") == "suppress"

    # Explicit bank context -> confident.
    assert _verdict("credited to account no. 123456789012 of the beneficiary") == "confident"
    assert _verdict("A/c 998877665544 held with IFSC SBIN0001234") == "confident"

    # No context either way -> still redacted, but flagged for a human.
    assert _verdict("reference 456789123456 appears in the annexure") == "needs_review"

    # SWIFT/BIC: the real corpus hit is accepted only because of its label.
    assert _swift_accepted("3 SWIFT Address of Financial Institution BARBINBBXXX 4 Full")
    assert not _swift_accepted("BARBINBBXXX appears with no label nearby")
    # Plain uppercase words match the shape but must never be redacted.
    assert not _swift_accepted("see ANNEXURE II for the list")
    assert not _swift_accepted("monitoring of ACCOUNTS held by the customer")
    # Lowercase prose and CBIC must not count as cues.
    assert not _swift_accepted("allow swift identification of ANNEXURE records")
    assert not _swift_accepted("the CBIC shall advise ANNEXURE dealers")

    # Document-level report: counts entities from placeholders, sorts most-exposed first.
    report = build_validation_report([
        {"doc_id": "doc_a", "source_file": "doc_a.pdf", "text": "x", "pii_redacted": False,
         "validation_flag": "confident"},
        {"doc_id": "doc_b", "source_file": "doc_b.pdf",
         "text": "at [REDACTED_PINCODE] and [REDACTED_EMAIL] plus [REDACTED_PINCODE]",
         "pii_redacted": True, "validation_flag": "needs_review"},
    ])
    assert [d["doc_id"] for d in report] == ["doc_b", "doc_a"], "most-exposed doc first"
    b, a = report
    assert b["pii_entities"] == 3 and b["distinct_entity_types"] == 2
    assert b["entity_types"] == {"PINCODE": 2, "EMAIL": 1}
    assert b["chunks_flagged_for_review"] == 1 and b["chunks_with_pii"] == 1
    assert a["pii_entities"] == 0 and a["entity_types"] == {} and a["chunks"] == 1

    print("ok: CIN + SWIFT cue + account validation + document report behave as expected")


if __name__ == "__main__":
    main()
