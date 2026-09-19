"""Self-check for Page-Splice Healing + the regulatory changelog.

Run: python -m pipeline.test_heal_changelog
"""
from collections import Counter

from pipeline.changelog import classify_edit, diff_versions, find_families
from pipeline.heal import find_furniture, remove_furniture, repair_ocr_splits


def _page(n: int, body: list) -> list:
    """One synthetic page: content lines, then the same footer every real PDF page gets."""
    return body + [f"Financial Intelligence Unit - India (FIU-IND) Page | {n}"]


def main():
    # --- Furniture: periodic footer removed, content kept ------------------------------
    lines = []
    for n in range(1, 13):
        body = [f"Clause {n}.{i} requires the reporting entity to verify identity." for i in range(30)]
        if n in (2, 3, 9):  # a real repeated sentence, but irregular and bunched
            body[5] = "Customer due diligence shall be applied at onboarding and review."
        lines += _page(n, body)
    furniture = find_furniture(lines)
    assert list(furniture) == ["financial intelligence unit - india (fiu-ind) page | #"], furniture

    healed, _, removed = remove_furniture("\n".join(lines))
    assert removed == 12, "exactly one footer per page removed"
    assert "FIU-IND" not in healed
    assert healed.count("Customer due diligence shall be applied") == 3, "content survives"
    assert healed.count("requires the reporting entity") == 12 * 30 - 3, "no content line dropped"

    # Frequent AND spread across the document, but irregularly bunched: content, kept.
    # This is the case frequency-based boilerplate removal gets wrong.
    doc = [f"unique line {i} of the policy text" for i in range(400)]
    for pos in (5, 9, 14, 20, 180, 186, 190, 330, 335, 390):
        doc[pos] = "Explanation: the expression beneficial owner has the meaning assigned"
    assert not find_furniture(doc), "irregular repetition must not be treated as furniture"

    # A table row reused once per SECTION (huge gaps) is content, not furniture.
    schema = []
    for _ in range(10):
        schema += ["1. First name First name of the account holder Yes"] + [f"row {i}" for i in range(400)]
    assert not find_furniture(schema)

    # --- OCR repair: merge kerning splits, never two real words ------------------------
    vocab = Counter({"financial": 40, "inancial": 1, "f": 2, "the": 90, "part": 30, "apart": 5, "a": 200})
    text, repairs = repair_ocr_splits("the f inancial year is a part of it", vocab)
    assert text == "the financial year is a part of it", text
    assert repairs == ["f inancial -> financial"]

    # --- Edit classification: cosmetic vs substantive ----------------------------------
    assert classify_edit("1. ―Know Your Customer", "1. “Know Your Customer") == "typography"
    assert classify_edit("Customer Identification Procedure (CIP) 15-47 4.",
                         "Customer Identification Procedure (CIP) 15-48 4.") == "pagination"
    assert classify_edit(
        "Procedure for implementation of Section 51A of 99 - 109 the Unlawful Activities Act, 1967 15.",
        "Procedure for implementation of Section 51A of 100 - 110 the Unlawful Activities Act, 1967 15.",
    ) == "pagination", "uniform +1 shift across a long TOC line"
    assert classify_edit(
        "incorporating amendments notified by Reserve Bank of India till 04.01.2024 in its Master Direction",
        "incorporating amendments notified by Reserve Bank of India till 06.11.2024 in its Master Direction",
    ) == "numeric", "a real date change must stay substantive"
    assert classify_edit(
        "cash transactions above Rs. 50,000 in a single day shall be reported to the principal officer",
        "cash transactions above Rs. 1,00,000 in a single day shall be reported to the principal officer",
    ) == "numeric", "a threshold change must stay substantive"
    assert classify_edit("there should be no need for a fresh CDD exercise",
                         "there shall be no need for a fresh CDD exercise") == "wording"

    # --- Diff: an edited clause that also MOVED pairs as one modification --------------
    old = ("Scope applies to all accounts. High risk accounts need closer monitoring. "
           "If an existing customer opens another account in the same bank, no fresh CDD is needed.")
    new = ("If an existing customer opens another account or product at any branch, no fresh CDD is needed. "
           "Scope applies to all accounts. CDD shall be applied at the UCIC level.")
    result = diff_versions(old, new)
    kinds = Counter(c.get("kind", c["type"]) for c in result["changes"])
    assert kinds == {"wording": 1, "removed": 1, "added": 1}, kinds
    assert result["sentences"]["unchanged"] == 1

    # --- Families: versions linked, an excerpt of the source is not --------------------
    base = " ".join(f"provision {i} requires customer verification before account opening" for i in range(300))
    docs = {
        "policy_2024": base,
        "policy_2025": base + " provision 300 adds a new requirement for periodic updation",
        "excerpt_2025": " ".join(base.split()[:600]),
    }
    assert find_families(docs) == [["policy_2024", "policy_2025"]], find_families(docs)

    print("ok: furniture detection, OCR repair, edit classification, diff pairing, families")


if __name__ == "__main__":
    main()
