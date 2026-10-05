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

This stage is our own rule-based filter, not a NeMo Curator stage. Real NeMo Curator 1.3.0
heuristic filters were run on this stage's input for comparison (pipeline/nemo_compare.py), and
the real nvidia/quality-classifier-deberta was tested and rejected as a hard filter
(docs/A1_4_quality_classifier_comparison.md); it is available only as an optional SIGNAL field
(QUALITY_SIGNAL_MODE below), never as a filter.
"""
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

# ---------------------------------------------------------------------------
# PATHS (match existing codebase convention)
# ---------------------------------------------------------------------------

DEDUPED_DIR = Path(__file__).resolve().parent.parent / "data" / "deduped"
FILTERED_DIR = Path(__file__).resolve().parent.parent / "data" / "filtered"
STAGE_RECORD_PATH = FILTERED_DIR / "_stage_record.json"
IN_PATH = DEDUPED_DIR / "chunks.jsonl"
OUT_PATH = FILTERED_DIR / "chunks.jsonl"
QUALITY_SIGNAL_CACHE_PATH = DEDUPED_DIR.parent / "quality_signal_cache.json"

# ---------------------------------------------------------------------------
# TUNABLE CONSTANTS — change these, not the logic  (B1.2)
# ---------------------------------------------------------------------------

# Existing heuristic thresholds (preserved from v1)
MIN_WORDS = 15
MAX_SYMBOL_RATIO = 0.3
MIN_ALPHA_RATIO = 0.5
# Was 0.30. That value only passed form tables (FIU reporting formats) because every page
# footer added ~a dozen "unique" words; once page-splice healing removed the footers, 166
# valid form chunks fell below it. 0.20 still removes stutter/loop/menu-spam junk (scores
# <= 0.06) and small-vocabulary junk down to ~0.17 (tested on synthetic junk).
MIN_LEXICAL_DIVERSITY = 0.20
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

# Pruned in Phase 4 because they are ordinary English/legal words in this corpus, not regulatory
# signals: placement, integration, trust, foundation, structuring, layering, passport,
# gazette notification. (Measured alone-tagging on 2047 chunks: passport 8, trust 5,
# foundation 1, structuring 1, the rest 0; see docs/IMPROVEMENT_LOG.md.)
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

    # Account & transaction surveillance
    "high risk", "high-risk", "risk categorisation", "risk category",
    "risk based approach", "risk profile",
    "unusual transaction", "suspicious transaction",
    "large cash transaction",
    "smurfing",

    # Identity document types (Indian)
    "aadhaar", "pan card", "voter id", "driving licence",
    "ckycr", "ckyc", "central kyc",

    # Customer categories with elevated scrutiny
    "nri", "foreign national", "non-resident", "correspondent banking",
    "shell company", "shell bank", "nominee director",
    "ngo",

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

# One pattern for all keywords. Each candidate is the LONGEST keyword that starts at a position
# and ends on a word boundary, found with a zero-width lookahead so candidates may overlap;
# overlaps are then resolved in _keyword_spans (longest wins).
_KEYWORD_PATTERN = re.compile(
    r"(?<!\w)(?=("
    + "|".join(re.escape(kw) for kw in sorted(REGULATORY_KEYWORDS, key=len, reverse=True))
    + r")(?!\w))",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# RULE 1 — Regulatory-keyword tagger  (B0.1-B0.4)
# RULE 2 — Regulatory-density score   (B1.1)
# ---------------------------------------------------------------------------

def _keyword_spans(text: str) -> list:
    """Non-overlapping keyword matches as (start, end, keyword), longest match wins (earlier on
    ties), ordered by start. So "aml/cft" counts once, not as "aml" plus "aml/cft", and
    "customer due diligence" does not also count "due diligence"."""
    candidates = [(m.start(1), m.end(1), m.group(1).lower()) for m in _KEYWORD_PATTERN.finditer(text)]
    kept = []
    for start, end, keyword in sorted(candidates, key=lambda c: (-(c[1] - c[0]), c[0])):
        if all(end <= k_start or start >= k_end for k_start, k_end, _ in kept):
            kept.append((start, end, keyword))
    return sorted(kept)


def tag_regulatory_keywords(text: str) -> dict:
    """
    Return a dict of tagging metadata for one chunk's text.

    Fields returned (all ADDITIVE — never shadow existing chunk fields):
      regulatory_tagged         bool   True if >= MIN_KEYWORD_MATCHES_FOR_TAG distinct keywords
      regulatory_keywords_found list   Sorted unique matched keywords (lowercased)
      regulatory_density_score  float  Fraction of words that are keyword-bearing, counted on
                                       NON-overlapping matches so no word is counted twice
    """
    spans = _keyword_spans(text)
    matched = {keyword for _, _, keyword in spans}
    word_count = len(text.split()) or 1
    keyword_words = sum(len(keyword.split()) for _, _, keyword in spans)

    return {
        "regulatory_tagged": len(matched) >= MIN_KEYWORD_MATCHES_FOR_TAG,
        "regulatory_keywords_found": sorted(matched),
        "regulatory_density_score": round(min(1.0, keyword_words / word_count), 4),
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
    signal_on = QUALITY_SIGNAL_MODE != "off"
    signal_cache = _load_signal_cache() if signal_on else {}
    signal_counts = Counter()
    _SIGNAL_STATE.update(computed=0, model_error=None)

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

            # Phase 4: classifier as a signal only (additive field; null when off/unavailable)
            chunk["quality_classifier_label"] = quality_signal_label(chunk["text"], signal_cache) if signal_on else None
            if signal_on:
                signal_counts[chunk["quality_classifier_label"] or "unavailable"] += 1

            survivors.append(chunk)

    if signal_on and _SIGNAL_STATE["computed"]:
        _save_signal_cache(signal_cache)

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
        # Phase 4 additive fields: the classifier is a signal, never a filter
        "quality_signal_mode": QUALITY_SIGNAL_MODE,
        "quality_signal_labels": dict(signal_counts),
        "quality_signal_model_error": _SIGNAL_STATE["model_error"],
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


def _classifier_label(text: str) -> str:
    """Real nvidia/quality-classifier-deberta inference (CPU) for one chunk: 'Low', 'Medium'
    or 'High'. The only place the model is called; needs torch + transformers + the weights."""
    import torch
    _load_quality_classifier()
    inputs = _classifier_tokenizer(
        [text], return_tensors="pt", padding="longest", truncation=True
    ).to(_classifier_device)
    with torch.no_grad():
        outputs = _classifier_model(inputs["input_ids"], inputs["attention_mask"])
    predicted_class = torch.argmax(outputs, dim=1).item()
    return _classifier_config.id2label[predicted_class]


def quality_reason_curator(text: str):
    """
    Hard-filter use of the classifier (USE_REAL_QUALITY_CLASSIFIER, off).
    Maps 3-class output onto the reason_counts contract:
      Low    -> "low_quality_classifier" (removed)
      Medium, High -> passes
    NOTE: treating "Low" as the removal threshold is a judgment call made
    here, not a given from the model. docs/A1_4 found it removes 45% of this corpus
    (97% of the FIU reporting formats), so it must NOT be used as a filter here.
    """
    return "low_quality_classifier" if _classifier_label(text) == "Low" else None


# ---------------------------------------------------------------------------
# Classifier as a SIGNAL (Phase 4): never removes a chunk. Adds the metadata field
# `quality_classifier_label` ("Low"/"Medium"/"High", or null when unavailable) so a
# downstream user can decide. Off by default: the CPU run takes ~3000 s for 2247 chunks.
#   "off"   -> no labels, the cache is not even read (default; pipeline speed unchanged)
#   "cache" -> labels only from the cache; never loads the model (fast, reuses a past run)
#   "model" -> cache first, then the model for misses; if the model cannot load (no
#              transformers/torch/weights/network) it falls back to cache-only and says so
# The cache maps SHA-256(chunk text) -> label, so it survives re-chunking and re-ordering.
# ---------------------------------------------------------------------------
QUALITY_SIGNAL_MODE = "off"
CACHE_SAVE_EVERY = 100  # a full model pass takes ~50 min; do not lose it to a crash

_SIGNAL_STATE = {"computed": 0, "model_error": None}


def _text_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_signal_cache() -> dict:
    if not QUALITY_SIGNAL_CACHE_PATH.exists():
        return {}
    return json.loads(QUALITY_SIGNAL_CACHE_PATH.read_text(encoding="utf-8"))


def _save_signal_cache(cache: dict) -> None:
    QUALITY_SIGNAL_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUALITY_SIGNAL_CACHE_PATH.write_text(json.dumps(cache, indent=0, sort_keys=True), encoding="utf-8")


def quality_signal_label(text: str, cache: dict):
    """Classifier label for a chunk from the cache or (mode "model") the model; None if neither."""
    key = _text_key(text)
    if key in cache:
        return cache[key]
    if QUALITY_SIGNAL_MODE != "model" or _SIGNAL_STATE["model_error"]:
        return None
    try:
        label = _classifier_label(text)
    except Exception as exc:  # ImportError, missing weights, no network: degrade, but say so
        _SIGNAL_STATE["model_error"] = f"{type(exc).__name__}: {exc}"
        print(f"quality signal: model unavailable ({_SIGNAL_STATE['model_error']}); using cache only", file=sys.stderr)
        return None
    cache[key] = label
    _SIGNAL_STATE["computed"] += 1
    if _SIGNAL_STATE["computed"] % CACHE_SAVE_EVERY == 0:
        _save_signal_cache(cache)
    return label


if __name__ == "__main__":
    main()
