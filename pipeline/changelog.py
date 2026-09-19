"""Regulatory changelog: what actually changed between versions of the same document.

Version families are detected from content, not filenames: two documents are versions of
each other when most of one's 5-shingles appear in the other. Each family is ordered by
the latest year its text mentions, and consecutive versions are diffed sentence by
sentence, with word-level detail for modified sentences.

Runs on HEALED text (python -m pipeline.heal first). On raw text the Central Bank
2024-25 -> 2025-26 diff is dominated by a letterhead spliced in at different page breaks;
after healing those versions share 99% of their content, so what the diff reports is the
actual policy change. The same pairs are diffed on raw text too, as a noise baseline.

Run: python -m pipeline.changelog
"""
import difflib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLEANED_DIR = ROOT / "data" / "cleaned"
HEALED_DIR = ROOT / "data" / "healed"
OUT_PATH = HEALED_DIR / "regulatory_changelog.json"

# Versions of one document share >=0.71 of their shingles on this corpus; different
# banks' policies that copy the RBI Master Direction share at most 0.62. Containment
# alone would also link an excerpt to its source, so versions must be comparable in
# size too: the 2016 -> 2024 Master Direction grew to 1.8x (ratio 0.55), while the
# Aug-2025 excerpt is 0.24 of the full text.
FAMILY_CONTAINMENT = 0.7
FAMILY_MIN_SIZE_RATIO = 0.4
MODIFIED_SIMILARITY = 0.5  # word-set Jaccard for treating a removed+added pair as one edit
PAGINATION_MAX_WORDS = 10
MAX_PAGE_SHIFT = 5
COSMETIC_KINDS = ("typography", "pagination")
YEAR_RE = re.compile(r"\b(20[0-3]\d)\b")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;:])\s+(?=[A-Z(\d])")


def _load(directory: Path) -> dict:
    docs = {}
    for p in sorted(directory.glob("*.json")):
        record = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(record, dict) and "doc_id" in record:
            docs[record["doc_id"]] = record["text"]
    return docs


def _shingles(text: str, k: int = 5) -> set:
    words = re.findall(r"\w+", text.lower())
    return {" ".join(words[i : i + k]) for i in range(max(len(words) - k + 1, 1))}


def find_families(docs: dict) -> list:
    """Connected components of documents whose content mostly overlaps."""
    ids = sorted(docs)
    sh = {d: _shingles(docs[d]) for d in ids}
    parent = {d: d for d in ids}

    def root(d):
        while parent[d] != d:
            d = parent[d]
        return d

    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            small, big = sorted((len(sh[a]), len(sh[b])))
            if (
                small / big >= FAMILY_MIN_SIZE_RATIO
                and len(sh[a] & sh[b]) / small >= FAMILY_CONTAINMENT
            ):
                parent[root(a)] = root(b)

    groups = {}
    for d in ids:
        groups.setdefault(root(d), []).append(d)
    return [g for g in groups.values() if len(g) > 1]


def version_year(text: str) -> int:
    """Latest year a document mentions -- a document can't cite what came after it."""
    years = [int(y) for y in YEAR_RE.findall(text)]
    return max(years) if years else 0


def _sentences(text: str) -> list:
    return [s for s in SENTENCE_SPLIT_RE.split(" ".join(text.split())) if s]


def word_diff(before: str, after: str) -> str:
    a, b = before.split(), after.split()
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            out.append(" ".join(a[i1:i2]))
        if op in ("delete", "replace"):
            out.append("[-" + " ".join(a[i1:i2]) + "-]")
        if op in ("insert", "replace"):
            out.append("{+" + " ".join(b[j1:j2]) + "+}")
    return " ".join(out)


def _words(sentence: str) -> set:
    return set(re.findall(r"\w+", sentence.lower()))


def classify_edit(before: str, after: str) -> str:
    """Cosmetic kinds stay in the changelog but out of the substantive count.

    Numbers-only edits are NOT automatically cosmetic: in regulation a changed number is
    often the whole change (a threshold, a deadline). Only short TOC-style lines count as
    pagination drift.
    """
    tokens = lambda s: re.sub(r"[^\w\s]", "", s.lower()).split()  # noqa: E731
    if tokens(before) == tokens(after):
        return "typography"
    non_numeric = lambda s: [t for t in tokens(s) if not t.isdigit()]  # noqa: E731
    if non_numeric(before) != non_numeric(after):
        return "wording"

    # Numbers-only edit. A page inserted earlier shifts every later page number by the
    # SAME small offset; a real date or threshold change doesn't move numbers uniformly.
    nb = [int(n) for n in re.findall(r"\d+", before)]
    na = [int(n) for n in re.findall(r"\d+", after)]
    shifts = [a - b for b, a in zip(nb, na) if a != b] if len(nb) == len(na) else []
    uniform = bool(shifts) and len(set(shifts)) == 1 and 0 < abs(shifts[0]) <= MAX_PAGE_SHIFT
    # ponytail: a lone +1 in a short line still reads as pagination; long clauses need 2+ shifts
    if uniform and (len(shifts) >= 2 or len(after.split()) <= PAGINATION_MAX_WORDS):
        return "pagination"
    return "numeric"


def diff_versions(old_text: str, new_text: str) -> dict:
    old, new = _sentences(old_text), _sentences(new_text)
    norm = lambda s: " ".join(s.lower().split())  # noqa: E731
    matcher = difflib.SequenceMatcher(None, [norm(s) for s in old], [norm(s) for s in new], autojunk=False)
    unchanged, removed, added = 0, [], []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            unchanged += i2 - i1
        else:
            removed += old[i1:i2]
            added += new[j1:j2]

    # Pair edits across the whole document, not within one diff block: a rewritten
    # clause often also moves between versions.
    pool = [(n, _words(n)) for n in added]
    changes = []
    for o in removed:
        ow = _words(o)
        scores = [len(ow & nw) / len(ow | nw) if ow | nw else 0.0 for _, nw in pool]
        best = max(range(len(pool)), key=scores.__getitem__, default=None)
        if best is not None and scores[best] >= MODIFIED_SIMILARITY:
            n, _ = pool.pop(best)
            changes.append({
                "type": "modified", "kind": classify_edit(o, n),
                "before": o, "after": n, "diff": word_diff(o, n),
            })
        else:
            changes.append({"type": "removed", "before": o})
    changes += [{"type": "added", "after": n} for n, _ in pool]

    counts = Counter(c.get("kind", c["type"]) for c in changes)
    cosmetic = sum(counts[k] for k in COSMETIC_KINDS)
    return {
        "sentences": {"unchanged": unchanged, **counts},
        "substantive_changes": sum(counts.values()) - cosmetic,
        "cosmetic_changes": cosmetic,
        "changes": changes,
    }


def main():
    healed = _load(HEALED_DIR)
    if not healed:
        raise SystemExit("no healed documents -- run python -m pipeline.heal first")
    raw = _load(CLEANED_DIR)

    changelog = []
    for family in find_families(healed):
        ordered = sorted(family, key=lambda d: (version_year(healed[d]), d))
        for old_id, new_id in zip(ordered, ordered[1:]):
            result = diff_versions(healed[old_id], healed[new_id])
            baseline = diff_versions(raw[old_id], raw[new_id])
            changelog.append({
                "family": ordered,
                "from": old_id,
                "to": new_id,
                "from_year": version_year(healed[old_id]),
                "to_year": version_year(healed[new_id]),
                "sentences": result["sentences"],
                "substantive_changes": result["substantive_changes"],
                "cosmetic_changes": result["cosmetic_changes"],
                "raw_text_total_changes": baseline["substantive_changes"] + baseline["cosmetic_changes"],
                "changes": result["changes"],
            })

    OUT_PATH.write_text(json.dumps(changelog, indent=2, ensure_ascii=False), encoding="utf-8")
    for e in changelog:
        print(
            f"{e['from']} ({e['from_year']}) -> {e['to']} ({e['to_year']}): "
            f"raw-text changes {e['raw_text_total_changes']} -> healed {e['substantive_changes']} "
            f"substantive + {e['cosmetic_changes']} cosmetic  {e['sentences']}"
        )


if __name__ == "__main__":
    main()
