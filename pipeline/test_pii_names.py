"""Labelled set for title-gated name detection (initials and ALL-CAPS only).

Run: python -m pipeline.test_pii_names
Positives must be found; negatives (job titles, common words, shapes that belong to the
spaCy path) must NOT be. If a negative ever regresses, revert the rule: precision first.
"""
from pipeline import pii
from pipeline.pii import _title_gated_names, redact_names_batch

POSITIVES = {
    "signed by Shri R. K. Sharma today": "R. K. Sharma",
    "Smt. S. Lakshmi was present": "S. Lakshmi",
    "Dr. A. P. J. Abdul Kalam attended": "A. P. J. Abdul Kalam",
    "MR. SURESH KUMAR signed the form": "SURESH KUMAR",
    "Mrs. MEENA GUPTA, Manager": "MEENA GUPTA",
    "SHRI R. K. SHARMA appeared": "R. K. SHARMA",
    "Ms. P. Iyer.": "P. Iyer",
    "SMT. ANITA DESAI and others": "ANITA DESAI",
}

NEGATIVES = [
    "Mr. Managing Director",
    "Shri Joint Secretary",
    "MR. CHIEF MANAGER",
    "Dr. Principal Officer",
    "Smt. DIRECTOR GENERAL",
    "Shri Joint Secretary (IS.I)",
    "Ms. A. Section 12",           # initial + blocklisted word
    "Dr. NOTE THAT the customer",  # common words in capitals
    "MR. THE BANK shall",
    "MS OFFICE SUITE installed",   # "MS" without a dot is not a title
    "Shri R. K. by the bank",      # initials only, no surname
    "Mr. A. will attend",          # lowercase continuation, single initial
    "Mr. Suresh Kumar",            # plain Title-Case: the spaCy path's job, not this rule's
    "Mr. Customer Identification",
    "Mr. [REDACTED_EMAIL]",
    "Mr.\nR. K. Sharma",           # a title at the end of a line does not reach the next one
    "the Managing Director and R. K. Sharma",  # no title directly before the name
]


def main():
    for text, expected in POSITIVES.items():
        found = [span[2] for span in _title_gated_names(text)]
        assert found == [expected], (text, found)
    for text in NEGATIVES:
        assert _title_gated_names(text) == [], (text, _title_gated_names(text))

    # End to end, without spaCy: names are replaced, job titles are not, spans do not overlap.
    saved = pii._SPACY_AVAILABLE
    try:
        pii._SPACY_AVAILABLE = False
        counts, examples = {}, []
        text = "signed by Shri R. K. Sharma and MR. SURESH KUMAR; the Managing Director agreed"
        out = redact_names_batch([text], ["t"], counts, examples)[0]
    finally:
        pii._SPACY_AVAILABLE = saved
    assert out == (
        "signed by Shri [REDACTED_PERSON_NAME] and MR. [REDACTED_PERSON_NAME]; the Managing Director agreed"
    ), out
    assert counts == {"PERSON_NAME": 2} and len(examples) == 2

    print(f"ok: {len(POSITIVES)} positives found, {len(NEGATIVES)} negatives untouched")


if __name__ == "__main__":
    main()
