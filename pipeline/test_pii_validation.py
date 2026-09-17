"""Self-check for Stream C additions: CIN detection + account-number cross-field validation.

Run: python -m pipeline.test_pii_validation
Strings below are real spans from the corpus (public RBI/MHA circulars and bank policy
PDFs), plus synthetic account-context cases the corpus does not contain.
"""
from pipeline.pii import PATTERNS, _account_number_verdict

CIN_RE = dict(PATTERNS)["CIN"]
ACCOUNT_RE = dict(PATTERNS)["ACCOUNT_NUMBER"]


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

    print("ok: CIN detection + account cross-field validation behave as expected")


if __name__ == "__main__":
    main()
