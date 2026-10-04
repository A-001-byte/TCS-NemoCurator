"""Self-check for Page-Splice Healing + the regulatory changelog.

Run: python -m pipeline.test_heal_changelog
"""
import json
import tempfile
from collections import Counter
from pathlib import Path

from pipeline import dedup
from pipeline.changelog import classify_edit, diff_versions, find_families
from pipeline.heal import find_furniture, heal_documents, remove_furniture, repair_ocr_splits


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

    # --- heal_documents: pure, in-memory, contract-valid stage record ------------------
    def synthetic_doc(doc_id: str, topic: str) -> dict:
        lines = []
        for n in range(1, 13):
            lines += _page(n, [f"{topic} clause {n}.{i} requires verification of identity." for i in range(30)])
        text = "\n".join(lines)
        return {"doc_id": doc_id, "source_file": f"{doc_id}.pdf", "text": text, "lang": "en", "char_count": len(text)}

    originals = [synthetic_doc("doc_a", "Alpha"), synthetic_doc("doc_b", "Beta")]
    snapshot = [dict(d) for d in originals]
    healed_docs, stage, report = heal_documents(originals)

    assert originals == snapshot, "heal_documents must not mutate its input"
    assert [d["doc_id"] for d in healed_docs] == ["doc_a", "doc_b"]
    assert set(healed_docs[0]) == set(originals[0]), "record shape unchanged"
    assert stage["stage"] == "heal"
    assert stage["docs_in"] == stage["docs_out"] == 2 and stage["removed"] == 0
    assert stage["reason_counts"]["furniture_lines_removed"] == 24, "one footer per page, two docs"
    assert set(stage["reason_counts"]) == {"furniture_lines_removed", "furniture_signatures", "ocr_splits_repaired"}
    assert set(stage["before"]) == set(stage["after"]) and stage["before"]["total_chars"] > stage["after"]["total_chars"]
    assert all("FIU-IND" not in d["text"] for d in healed_docs)
    for after_doc in healed_docs:
        assert after_doc["char_count"] == len(after_doc["text"])
        assert after_doc["text"].count("requires verification") == 360, "no content line dropped"
    assert set(report) == {"before", "after", "documents"} and set(report["documents"]) == {"doc_a", "doc_b"}

    # --- dedup loads documents from data/healed, which also holds non-document JSON -----
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        (folder / "doc_a.json").write_text(json.dumps(originals[0]), encoding="utf-8")
        (folder / "heal_report.json").write_text(json.dumps(report), encoding="utf-8")
        (folder / "regulatory_changelog.json").write_text("[]", encoding="utf-8")
        (folder / "_stage_record.json").write_text(json.dumps(stage), encoding="utf-8")
        loaded = dedup._load_documents(folder)
    assert [d["doc_id"] for d in loaded] == ["doc_a"], "only real documents are loaded"

    print("ok: furniture detection, OCR repair, edit classification, diff pairing, families, heal stage, dedup loader")


if __name__ == "__main__":
    main()
