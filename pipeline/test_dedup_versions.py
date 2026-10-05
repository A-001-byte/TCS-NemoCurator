"""Self-check: dedup keeps the NEWEST policy version of a shared clause.

Run: python -m pipeline.test_dedup_versions
"""
from pipeline import dedup
from pipeline.versioning import document_year, filename_year, newest_first, version_year


def _doc(doc_id: str, text: str) -> dict:
    return {"doc_id": doc_id, "source_file": f"{doc_id}.pdf", "text": text, "lang": "en", "char_count": len(text)}


def _words(prefix: str, n: int) -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


def _survivors(documents: list) -> list:
    after_exact, _ = dedup._exact_dedup(dedup.build_chunks(documents))
    survivors, _, _ = dedup._fuzzy_dedup_with_boilerplate_awareness(after_exact)
    return [c["chunk_id"] for c in survivors]


def main():
    # --- Year from the filename: financial-year pairs, plain years, none ----------------
    assert filename_year("central_bank_india_kyc_aml_2024_25") == 2025
    assert filename_year("central_bank_india_kyc_aml_2025_26") == 2026
    assert filename_year("central_bank_india_kyc_aml_2021") == 2021
    assert filename_year("rbi_kyc_fidcindia_aug2025") == 2025
    assert filename_year("bhiwani_dccb_kyc_aml_cft_2023_24") == 2024
    assert filename_year("rbi_kyc_master_direction_slbc_mp") == 0
    assert filename_year("report_2023_28") == 2023, "2023_28 is not a financial-year pair"

    # --- Text fallback, and the documented caveat ---------------------------------------
    assert version_year("amended in 2019 and again in 2022") == 2022
    assert document_year("policy_2021", "mentions a deadline in 2030") == 2021, "filename beats text"
    assert document_year("policy", "updated 2019, effective by 2027") == 2027, "caveat: max year in text"
    assert document_year("policy", "no year at all") == 0

    # --- Ordering: newest first, deterministic ties -------------------------------------
    docs = [_doc("policy_2021", "x"), _doc("zeta", "none"), _doc("policy_2025", "x"), _doc("alpha", "none")]
    assert [d["doc_id"] for d in newest_first(docs)] == ["policy_2025", "policy_2021", "alpha", "zeta"]
    assert newest_first(docs) == newest_first(list(reversed(docs))), "input order must not matter"

    # --- A clause shared by two versions survives in the NEWER one ----------------------
    shared = _words("clause", 180)  # exactly one chunk, identical in both versions
    old = _doc("policy_2021", shared + " " + _words("oldonly", 200))
    new = _doc("policy_2025", shared + " " + _words("newonly", 200))
    kept = _survivors([old, new])  # oldest first on purpose
    assert "policy_2025__0" in kept and "policy_2021__0" not in kept, kept
    assert "policy_2021__1" in kept and "policy_2025__1" in kept, "each version keeps what is unique to it"
    assert _survivors([new, old]) == kept, "same result whichever way round the input arrives"
    assert _survivors([old, new]) == _survivors([old, new]), "deterministic"

    print("ok: version years, newest-first ordering, shared clause kept from the newest version")


if __name__ == "__main__":
    main()
