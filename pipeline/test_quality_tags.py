"""Self-check for the regulatory tagger: pruned keywords, overlap-free matching, boundaries.

Run: python -m pipeline.test_quality_tags
"""
from pipeline import quality
from pipeline.quality import REGULATORY_KEYWORDS, tag_regulatory_keywords

PRUNED = ("placement", "integration", "trust", "foundation", "structuring", "layering",
          "passport", "gazette notification")


def main():
    # --- Generic words were pruned and stay pruned ----------------------------------------
    assert not set(PRUNED) & REGULATORY_KEYWORDS
    for text in ("the trustee of the trust", "passport office placement and integration",
                 "a foundation for structuring layering", "per the gazette notification"):
        assert tag_regulatory_keywords(text)["regulatory_keywords_found"] == [], text
    # Specific multi-word phrases survive
    for kept in ("beneficial owner", "anti-money laundering", "customer due diligence",
                 "suspicious transaction"):
        assert tag_regulatory_keywords(f"the {kept} rules")["regulatory_keywords_found"] == [kept], kept

    # --- Overlaps: each word counted once, longest match wins -----------------------------
    tags = tag_regulatory_keywords("aml/cft framework")
    assert tags["regulatory_keywords_found"] == ["aml/cft"]
    assert tags["regulatory_density_score"] == 0.5, "old code counted aml + aml/cft = 1.0"
    tags = tag_regulatory_keywords("customer due diligence is required")
    assert tags["regulatory_keywords_found"] == ["customer due diligence"]
    assert tags["regulatory_density_score"] == 0.6
    assert tag_regulatory_keywords("know your customer due diligence")["regulatory_keywords_found"] == [
        "customer due diligence"], "partial overlap: the longer phrase wins"
    assert tag_regulatory_keywords("re-kyc of the account")["regulatory_keywords_found"] == ["re-kyc"]
    assert tag_regulatory_keywords("kyc kyc kyc")["regulatory_density_score"] == 1.0, "capped at 1"
    assert tag_regulatory_keywords("KYC and Aadhaar")["regulatory_keywords_found"] == ["aadhaar", "kyc"]

    # --- Word boundaries, including multi-word keywords ----------------------------------
    for text in ("foggrey listing", "the grey listing", "kycs and strategic plans", "the recipient"):
        assert tag_regulatory_keywords(text)["regulatory_keywords_found"] == [], text
    assert tag_regulatory_keywords("the grey list.")["regulatory_keywords_found"] == ["grey list"]

    # --- A chunk of pure form boilerplate is untagged (real FIU field-description wording) -
    boilerplate = (
        "Primary Address Pin Code Please Note Portal Indian Addresses The Pin-code will be a free "
        "text field and mandatory field will become non-mandatory Bulk files Separate fields are "
        "provisioned for Indian and Non-Indian addresses Secondary Address State as part of address"
    )
    tags = tag_regulatory_keywords(boilerplate)
    assert tags["regulatory_keywords_found"] == [] and not tags["regulatory_tagged"]
    assert tags["regulatory_density_score"] == 0.0

    # --- The tag threshold: the owner chose 2 distinct keywords; repeats do not count ------
    assert quality.MIN_KEYWORD_MATCHES_FOR_TAG == 2
    assert not tag_regulatory_keywords("only kyc here")["regulatory_tagged"]
    assert not tag_regulatory_keywords("kyc kyc kyc kyc")["regulatory_tagged"], "repeats are one keyword"
    assert tag_regulatory_keywords("kyc and aml here")["regulatory_tagged"]
    saved = quality.MIN_KEYWORD_MATCHES_FOR_TAG
    try:
        quality.MIN_KEYWORD_MATCHES_FOR_TAG = 3
        assert not tag_regulatory_keywords("kyc and aml here")["regulatory_tagged"]
        assert tag_regulatory_keywords("kyc and aml and cdd here")["regulatory_tagged"]
    finally:
        quality.MIN_KEYWORD_MATCHES_FOR_TAG = saved

    print("ok: pruned keywords, overlap-free density, word boundaries, tag threshold")


if __name__ == "__main__":
    main()
