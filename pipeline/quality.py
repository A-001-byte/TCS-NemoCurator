"""
pipeline/quality.py  —  Stage 4: heuristic quality filtering + Stream B additions
==================================================================================
Reads data/deduped/chunks.jsonl, writes surviving chunks to data/filtered/chunks.jsonl.

Original heuristic quality filter (word count, alpha ratio, symbol ratio,
lexical diversity) is preserved unchanged below the "EXISTING LOGIC" marker.

Stream B adds TWO domain-specific custom rules on top:

  Rule 1 — Regulatory-keyword routing  (B0.1-B0.4)
    Tags every surviving chunk with whether it contains >=1 BFSI/regulatory
    keyword (KYC, AML, STR, PEP, UBO, CDD, EDD, etc.). This is an ADDITIVE
    field (regulatory_tagged, regulatory_keywords_found,
    regulatory_density_score) — it never removes chunks and never touches
    existing fields.

  Rule 2 — Regulatory-density score  (B1.1)
    What fraction of a chunk's words are regulatory-keyword-bearing. Stored
    as regulatory_density_score (float 0.0-1.0). Useful as a signal for
    Stream D's pattern-matching work.

WHY these rules are BFSI-specific, not generic NLP hygiene:
  - The keyword list maps to specific Indian regulatory regimes (RBI, FIU-IND,
    PMLA 2002, FATF guidelines). None of these terms appear in generic text
    quality filters. A chunk that passes all generic quality checks but
    contains zero regulatory terms is not the type of content this corpus is
    being curated to train on.
  - The density score distinguishes a chunk that's mostly procedural KYC
    obligation text from one that merely mentions "KYC" once in a header.
    Both pass generic quality filters; only one is genuinely useful training
    signal for a BFSI-domain LLM.

NeMo-Curator-equivalent stage, library integration pending (Stream A).
"""
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# PATHS (match existing codebase convention)
# ---------------------------------------------------------------------------

DEDUPED_DIR = Path(__file__).resolve().parent.parent / "data" / "deduped"
FILTERED_DIR = Path(__file__).resolve().parent.parent / "data" / "filtered"
STAGE_RECORD_PATH = FILTERED_DIR / "_stage_record.json"
IN_PATH = DEDUPED_DIR / "chunks.jsonl"
OUT_PATH = FILTERED_DIR / "chunks.jsonl"

# ---------------------------------------------------------------------------
# TUNABLE CONSTANTS — change these, not the logic  (B1.2)
# ---------------------------------------------------------------------------

# Existing heuristic thresholds (preserved from v1)
MIN_WORDS = 15
MAX_SYMBOL_RATIO = 0.3
MIN_ALPHA_RATIO = 0.5
MIN_LEXICAL_DIVERSITY = 0.30
WORD_RE = re.compile(r"\w+")
ALPHA_RE = re.compile(r"[A-Za-z]")

# Stream B — regulatory keyword routing thresholds
MIN_KEYWORD_MATCHES_FOR_TAG = 1
HIGH_DENSITY_THRESHOLD = 0.05   # 5% of words are regulatory-keyword-bearing

# ---------------------------------------------------------------------------
# REGULATORY KEYWORD LIST  (B0.1)
# Covers Indian BFSI regulatory vocabulary: RBI Master Directions, PMLA 2002,
# FATF recommendations, FIU-IND reporting, SEBI AML, IBA guidelines.
# ---------------------------------------------------------------------------

REGULATORY_KEYWORDS = {
    # Core KYC/AML programme terms
    "kyc", "aml", "cft", "aml/cft", "anti-money laundering",
    "counter financing of terrorism", "counter-terrorism financing",
    "know your customer",

    # Reporting instrument types
    "str", "ctr", "sar", "suspicious transaction report",
    "cash transaction report", "suspicious activity report",
    "ntr", "ccr", "rtr",

    # Customer due diligence tiers
    "cdd", "edd", "sdd", "customer due diligence",
    "enhanced due diligence", "simplified due diligence",

    # Beneficial ownership & political exposure
    "ubo", "beneficial owner", "beneficial ownership",
    "pep", "politically exposed person",
    "close associate", "family member of pep",

    # Watchlist / sanctions
    "sanctions", "sanctioned", "ofac", "un sanctions",
    "fatf", "blacklist", "grey list",
    "designated entity", "designated individual",

    # Indian regulatory bodies & instruments
    "rbi", "fiu-ind", "fiu", "pmla", "prevention of money laundering",
    "sebi", "irdai", "pfrda",
    "master direction", "master circular", "rbi circular",
    "gazette notification",

    # Account & transaction surveillance
    "high risk", "high-risk", "risk categorisation", "risk category",
    "risk based approach", "risk profile",
    "unusual transaction", "suspicious transaction",
    "large cash transaction", "structuring",
    "smurfing", "layering", "placement", "integration",

    # Identity document types (Indian)
    "aadhaar", "pan card", "passport", "voter id", "driving licence",
    "ckycr", "ckyc", "central kyc",

    # Customer categories with elevated scrutiny
    "nri", "foreign national", "non-resident", "correspondent banking",
    "shell company", "shell bank", "nominee director",
    "trust", "foundation", "ngo",

    # Process / compliance terms
    "onboarding", "re-kyc", "re kyc", "periodic review", "periodic updation",
    "account opening", "due diligence",
    "customer identification", "customer identification procedure", "cip",
    "record keeping", "record retention",
    "training and awareness", "compliance officer",
    "internal audit", "concurrent audit",
    "reporting entity", "principal officer",
    "designated director",
}

# Pre-compile patterns for keyword matching
_SINGLE_TOKEN_KW = {kw for kw in REGULATORY_KEYWORDS if " " not in kw and "/" not in kw}
_MULTI_TOKEN_KW  = REGULATORY_KEYWORDS - _SINGLE_TOKEN_KW

_SINGLE_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(kw) for kw in sorted(_SINGLE_TOKEN_KW, key=len, reverse=True)) + r')\b',
    re.IGNORECASE,
)
_MULTI_PATTERN = re.compile(
    '(' + '|'.join(re.escape(kw) for kw in sorted(_MULTI_TOKEN_KW, key=len, reverse=True)) + ')',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# RULE 1 — Regulatory-keyword tagger  (B0.1-B0.4)
# RULE 2 — Regulatory-density score   (B1.1)
# ---------------------------------------------------------------------------

def tag_regulatory_keywords(text: str) -> dict:
    """
    Return a dict of tagging metadata for one chunk's text.

    Fields returned (all ADDITIVE — never shadow existing chunk fields):
      regulatory_tagged         bool   True if >= MIN_KEYWORD_MATCHES_FOR_TAG hits
      regulatory_keywords_found list   Sorted unique matched keywords (lowercased)
      regulatory_density_score  float  Fraction of words that are keyword-bearing
    """
    text_lower = text.lower()
    matched = set()

    for m in _SINGLE_PATTERN.finditer(text_lower):
        matched.add(m.group(0).lower())
    for m in _MULTI_PATTERN.finditer(text_lower):
        matched.add(m.group(0).lower())

    # Density score: count word-tokens covered by any keyword match
    words = text_lower.split()
    word_count = len(words) if words else 1
    kw_bearing_token_count = 0
    all_matches_text = list(_SINGLE_PATTERN.finditer(text_lower)) + list(_MULTI_PATTERN.finditer(text_lower))
    for m in all_matches_text:
        kw_bearing_token_count += len(m.group(0).split())

    density = min(1.0, kw_bearing_token_count / word_count)

    return {
        "regulatory_tagged": len(matched) >= MIN_KEYWORD_MATCHES_FOR_TAG,
        "regulatory_keywords_found": sorted(matched),
        "regulatory_density_score": round(density, 4),
    }


# ---------------------------------------------------------------------------
# EXISTING HEURISTIC QUALITY FILTER (v1, preserved unchanged)
# ---------------------------------------------------------------------------

def quality_reason(text: str):
    """
    Returns rejection reason string, or None if chunk passes.
    Reasons map to the existing stage-record reason_counts keys.
    """
    words = WORD_RE.findall(text)
    if len(words) < MIN_WORDS:
        return "too_few_words"

    alpha_chars = len(ALPHA_RE.findall(text))
    if alpha_chars / max(len(text), 1) < MIN_ALPHA_RATIO:
        return "low_alpha_ratio"

    symbol_chars = sum(1 for c in text if not c.isalnum() and not c.isspace())
    if symbol_chars / max(len(text), 1) > MAX_SYMBOL_RATIO:
        return "high_symbol_ratio"

    unique_words = set(w.lower() for w in words)
    if len(unique_words) / len(words) < MIN_LEXICAL_DIVERSITY:
        return "low_lexical_diversity"

    return None


# ---------------------------------------------------------------------------
# MAIN ENTRY POINT (called by pipeline/run.py)
# ---------------------------------------------------------------------------

def main():
    FILTERED_DIR.mkdir(parents=True, exist_ok=True)
    if not IN_PATH.exists():
        print(json.dumps({"stage": "quality_filter", "error": "no input chunks"}))
        sys.exit(1)

    chunks_in = 0
    survivors = []
    reason_counts = {}
    regulatory_tagged_count = 0
    regulatory_untagged_count = 0
    high_density_count = 0

    with IN_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            chunk = json.loads(line)
            chunks_in += 1

            # --- Existing heuristic filter ---
            reason = quality_reason_curator(chunk["text"]) if USE_REAL_QUALITY_CLASSIFIER else quality_reason(chunk["text"])
            if reason:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
                continue

            # --- Stream B: regulatory keyword tagging (additive fields only) ---
            tag_info = tag_regulatory_keywords(chunk["text"])
            chunk["regulatory_tagged"]         = tag_info["regulatory_tagged"]
            chunk["regulatory_keywords_found"] = tag_info["regulatory_keywords_found"]
            chunk["regulatory_density_score"]  = tag_info["regulatory_density_score"]

            if tag_info["regulatory_tagged"]:
                regulatory_tagged_count += 1
            else:
                regulatory_untagged_count += 1

            if tag_info["regulatory_density_score"] >= HIGH_DENSITY_THRESHOLD:
                high_density_count += 1

            survivors.append(chunk)

    with OUT_PATH.open("w", encoding="utf-8") as f:
        for chunk in survivors:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    record = {
        "stage": "quality_filter",
        "docs_in": chunks_in,
        "docs_out": len(survivors),
        "removed": chunks_in - len(survivors),
        "reason_counts": reason_counts,
        # Stream B additive fields (B0.3)
        "regulatory_tagged_count": regulatory_tagged_count,
        "regulatory_untagged_count": regulatory_untagged_count,
        "high_density_count": high_density_count,
    }
    STAGE_RECORD_PATH.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps(record, indent=2))

    if len(survivors) == 0:
        sys.exit(1)



# ---------------------------------------------------------------------------
# STREAM A — Real quality classifier (nvidia/quality-classifier-deberta)
#
# Run via plain `transformers`, NOT via NeMo Curator's ProcessingStage /
# DistributedDataClassifier. NVIDIA's own docs state that distributed
# classification "requires GPU acceleration and is not supported for
# CPU-only processing." This machine has no NVIDIA GPU. This is still the
# real model and real weights -- just invoked directly instead of through
# Curator's GPU-only wrapper. Documented in SETUP.md.
# ---------------------------------------------------------------------------

USE_REAL_QUALITY_CLASSIFIER = False  # flip True to use real model instead of heuristic

_classifier_model = None
_classifier_tokenizer = None
_classifier_config = None
_classifier_device = None


def _load_quality_classifier():
    global _classifier_model, _classifier_tokenizer, _classifier_config, _classifier_device
    if _classifier_model is not None:
        return
    import torch
    from torch import nn
    from transformers import AutoModel, AutoTokenizer, AutoConfig
    from huggingface_hub import PyTorchModelHubMixin

    class QualityModel(nn.Module, PyTorchModelHubMixin):
        def __init__(self, config):
            super().__init__()
            self.model = AutoModel.from_pretrained(config["base_model"])
            self.dropout = nn.Dropout(config["fc_dropout"])
            self.fc = nn.Linear(self.model.config.hidden_size, len(config["id2label"]))

        def forward(self, input_ids, attention_mask):
            features = self.model(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
            dropped = self.dropout(features)
            return torch.softmax(self.fc(dropped)[:, 0, :], dim=1)

    _classifier_device = "cuda" if torch.cuda.is_available() else "cpu"
    _classifier_config = AutoConfig.from_pretrained("nvidia/quality-classifier-deberta")
    _classifier_tokenizer = AutoTokenizer.from_pretrained("nvidia/quality-classifier-deberta")
    _classifier_model = QualityModel.from_pretrained("nvidia/quality-classifier-deberta").to(_classifier_device)
    _classifier_model.eval()


def quality_reason_curator(text: str):
    """
    Real nvidia/quality-classifier-deberta inference (CPU).
    Maps 3-class output onto the reason_counts contract:
      Low    -> "low_quality_classifier" (removed)
      Medium, High -> passes
    NOTE: treating "Low" as the removal threshold is a judgment call made
    here, not a given from the model -- state this plainly when reporting
    A1.4 comparison results.
    """
    import torch
    _load_quality_classifier()
    inputs = _classifier_tokenizer(
        [text], return_tensors="pt", padding="longest", truncation=True
    ).to(_classifier_device)
    with torch.no_grad():
        outputs = _classifier_model(inputs["input_ids"], inputs["attention_mask"])
    predicted_class = torch.argmax(outputs, dim=1).item()
    predicted_label = _classifier_config.id2label[predicted_class]
    return "low_quality_classifier" if predicted_label == "Low" else None


if __name__ == "__main__":
    main()
