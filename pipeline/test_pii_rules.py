"""Self-check for the Phase 3 PII rules: DATE cue gate, PINCODE context, AADHAAR checksum.

Run: python -m pipeline.test_pii_rules
Strings marked (real) are spans from the actual corpus; Aadhaar numbers are generated with
the Verhoeff algorithm, never hard-coded guesses (the corpus has no Aadhaar numbers).
"""
import re

from pipeline.pii import redact_regex, verhoeff_valid


def run(text: str):
    counts, validation = {}, {}
    redacted = redact_regex(text, counts, [], "t", validation)
    return redacted, counts, validation


def aadhaar(base11: str, valid: bool = True) -> str:
    """12-digit number from an 11-digit base: with its Verhoeff check digit, or a wrong one."""
    ok = [d for d in "0123456789" if verhoeff_valid(base11 + d)]
    assert len(ok) == 1, "exactly one check digit makes a Verhoeff number valid"
    return base11 + (ok[0] if valid else next(d for d in "0123456789" if d != ok[0]))


def spaced(n: str) -> str:
    return f"{n[:4]} {n[4:8]} {n[8:]}"


def main():
    # --- Known Verhoeff test vector (independent of the generator below) ----------------
    assert verhoeff_valid("2363") and not verhoeff_valid("2364")

    # --- DATE: public regulatory dates are kept (real spans) ----------------------------
    for kept in (
        "Also, on 18/11/2019, RBI had imposed penalty for not undertaking",
        "KYC-AML-CFT POLICY-2023-24 Updated as on 15-01-2024 1. Introduction",
        "As per UIDAI circular dated 23-10-2018 based on the opinion",
        "RBI style date 18.11.2019 in a circular",
    ):
        out, counts, validation = run(kept)
        assert out == kept and "DATE" not in counts, kept
        assert validation["date_no_cue"] == 1

    # --- DATE: birth dates are redacted, any separator, 1-2 digit day/month -------------
    for text in (
        "DOB: 12/03/1990 of the customer",
        "Date of Birth 12.03.1990 of the customer",
        "applicant born on 5-6-1985 in Pune",
        "D.O.B 12-03-1990",
        "dob 12/03/1990",
    ):
        out, counts, _ = run(text)
        assert counts == {"DATE": 1} and "[REDACTED_DATE]" in out, text
    out, counts, _ = run("Date of Birth\n12/03/1990")
    assert "DATE" not in counts, "a cue on the previous line does not count"
    assert "DATE" not in run("DOB 12/03-1990")[1], "mixed separators are not a date"

    # --- PINCODE: addresses are redacted (real spans + label forms) ---------------------
    for text in (
        "G.B. Pant Road, Nainital, Uttarakhand-263001 CIN No.",
        "North Block, New Delhi – 110001 or through email",
        "Mandvi,Baroda- 390006. Telephone Number",
        "Alkapuri,Vadodara, G ujarat-390007 Telephone",
        "Registered office PIN: 400001",
        "Pincode 400001",
        "PIN code - 400001",
        "Pin No. 400001",
    ):
        out, counts, _ = run(text)
        assert counts == {"PINCODE": 1}, text

    # --- PINCODE: money, phone tails and impossible prefixes are kept -------------------
    for text in (
        "Accounts Rural 75000 50000 25000 Semi Urban 100000 75000 50000 Urban 150000",  # (real)
        "Phone: 05942-233739 DOCUMENT CONTROL",  # (real) STD phone tail
        "transactions of Rs. 500000 or more",
        "above Rs 500000 in a day",
        "threshold of 100000 per month",
        "amount exceeding 100000",
        "Mumbai-100001",  # prefix 10 does not exist
    ):
        out, counts, validation = run(text)
        assert out == text and "PINCODE" not in counts, text
        candidates = len(re.findall(r"\b[1-9]\d{5}\b", text))
        rejected = validation.get("pincode_no_cue", 0) + validation.get("pincode_other", 0)
        assert candidates >= 1 and rejected == candidates, text

    # --- AADHAAR: checksum-valid is redacted; no review flag ----------------------------
    good = aadhaar("23456789012")
    for text in (f"number {spaced(good)} on file", f"number {good} on file",
                 f"number {good[:4]}-{good[4:8]}-{good[8:]} on file"):
        out, counts, validation = run(text)
        assert counts == {"AADHAAR": 1} and "aadhaar_needs_review" not in validation, text

    # --- AADHAAR: checksum fails + Aadhaar label nearby -> redacted AND flagged ---------
    bad = aadhaar("23456789012", valid=False)
    out, counts, validation = run(f"Aadhaar number {spaced(bad)} of the customer")
    assert counts == {"AADHAAR": 1} and validation["aadhaar_needs_review"] == 1
    assert "[REDACTED_AADHAAR]" in run(f"UID: {spaced(bad)}")[0]

    # --- AADHAAR: checksum fails, no label -> left alone and counted --------------------
    text = f"table value {spaced(bad)} in the annexure"
    out, counts, validation = run(text)
    assert out == text and "AADHAAR" not in counts and validation["aadhaar_rejected"] == 1

    # --- AADHAAR: shapes that must never match ------------------------------------------
    for text in ("0000 0000 0000", "1234 5678 9012", f"{good[:4]} {good[4:8]}\n{good[8:]}"):
        assert "AADHAAR" not in run(text)[1], text

    print("ok: DATE cue gate, PINCODE context rules, AADHAAR checksum/cue policy")


if __name__ == "__main__":
    main()
