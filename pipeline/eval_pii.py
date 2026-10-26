"""Measure the PII stage against a labelled set, so "how much PII do we miss?" has a number.

    python -m pipeline.eval_pii                     # print the report
    python -m pipeline.eval_pii --write-doc         # rewrite docs/PII_RECALL.md
    python -m pipeline.eval_pii --check             # exit 1 if docs/PII_RECALL.md is out of date

The gold set (`evaluation/pii_gold.jsonl`) is synthetic: hand-written KYC-style sentences with known values,
awkward real-world spellings on purpose, plus hard negatives (circular dates, table figures, public phone numbers).
It measures how well the rules handle that kind of text. It is not a sample of real customer documents, so it does not
say how the stage performs on them.

Scoring, per item and per type:
  hit     the value no longer appears in the output, and a placeholder of the right type is there
  leak    the value is still present verbatim in the output (the serious failure)
  false alarm  a placeholder the gold set does not expect, on a positive or negative item
"public" items (official addresses and mailboxes printed in public documents) are scored apart: redacting them is
over-cautious, not a leak.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Callable, Optional

from pipeline import pii

ROOT = Path(__file__).resolve().parent.parent
GOLD_PATH = ROOT / "evaluation" / "pii_gold.jsonl"
DOC_PATH = ROOT / "docs" / "PII_RECALL.md"
TYPES = ("PAN", "AADHAAR", "EMAIL", "PHONE", "DATE", "PINCODE", "ACCOUNT_NUMBER", "SWIFT_BIC", "CIN", "PERSON_NAME")
KINDS = ("positive", "negative", "public")

Redactor = Callable[[str], tuple]  # text -> (redacted text, Counter of placeholder types)


def load_gold(path: Path = GOLD_PATH) -> list:
    items = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [item["id"] for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate ids in the gold set")
    for item in items:
        if item["kind"] not in KINDS:
            raise ValueError(f"{item['id']}: unknown kind {item['kind']!r}")
        for kind, value in item["pii"]:
            if kind not in TYPES:
                raise ValueError(f"{item['id']}: unknown type {kind!r}")
            if value not in item["text"]:
                raise ValueError(f"{item['id']}: value {value!r} is not in the text")
    return items


def stage_redactor() -> Redactor:
    """The PII stage's own rules (regex, then names), in the stage's order."""
    pii._load_spacy()

    def redact(text: str) -> tuple:
        counts, examples, validation = {}, [], {}
        once = pii.redact_regex(text, counts, examples, "gold", validation)
        redacted = pii.redact_names_batch([once], ["gold"], counts, examples)[0]
        placeholders = Counter(m.group(1) for m in pii.REDACTION_PLACEHOLDER_RE.finditer(redacted))
        return redacted, placeholders

    return redact


def evaluate(items: list, redact: Optional[Redactor] = None) -> dict:
    redact = redact or stage_redactor()
    per_type = {t: Counter() for t in TYPES}
    misses, false_alarms, public_hits = [], [], []
    for item in items:
        redacted, placeholders = redact(item["text"])
        expected = Counter(kind for kind, _ in item["pii"])
        if item["kind"] == "public":
            if placeholders:
                public_hits.append({"id": item["id"], "placeholders": dict(placeholders)})
            continue
        for kind in TYPES:
            hit = min(placeholders[kind], expected[kind])
            per_type[kind]["expected"] += expected[kind]
            per_type[kind]["hit"] += hit
            per_type[kind]["false_alarm"] += max(0, placeholders[kind] - expected[kind])
        leaked = [(kind, value) for kind, value in item["pii"] if value in redacted]
        for kind, _ in leaked:
            per_type[kind]["leak"] += 1
        wrong = {k: n - expected[k] for k, n in placeholders.items() if n > expected[k]}
        if wrong:
            false_alarms.append({"id": item["id"], "unexpected": wrong, "kind": item["kind"]})
        if leaked or any(expected[k] > placeholders[k] for k in expected):
            misses.append({"id": item["id"], "expected": [list(p) for p in item["pii"]], "output": redacted})

    totals = Counter()
    for counter in per_type.values():
        totals.update(counter)
    return {
        "items": {kind: sum(1 for i in items if i["kind"] == kind) for kind in KINDS},
        "per_type": {t: dict(c) for t, c in per_type.items() if c["expected"] or c["false_alarm"]},
        "totals": dict(totals),
        "misses": misses,
        "false_alarms": false_alarms,
        "public_redacted": public_hits,
    }


def _ratio(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "n/a"


def report(result: dict) -> str:
    totals = result["totals"]
    expected, hit, leak, alarms = (totals.get(k, 0) for k in ("expected", "hit", "leak", "false_alarm"))
    lines = [
        "# PII recall and precision",
        "",
        "Generated by `python -m pipeline.eval_pii --write-doc` from `evaluation/pii_gold.jsonl`. Do not edit by hand.",
        "",
        "## What this measures, and what it does not",
        "",
        f"The gold set is **synthetic**: {result['items']['positive']} hand-written KYC-style sentences with known values, "
        f"{result['items']['negative']} hard negatives (circular dates, table figures, public phone numbers, job titles) and "
        f"{result['items']['public']} items of public contact details. Spellings are awkward on purpose (grouped phone numbers, "
        "lower-case PAN, no honorific before a name). It tests the rules on that kind of text. It is **not** a sample of real "
        "customer documents, so it cannot say how many real names or numbers the stage misses in the wild.",
        "",
        "## Result",
        "",
        f"- Values hidden with the right placeholder: **{hit} of {expected} ({_ratio(hit, expected)})**",
        f"- Values still visible in the output (leaks): **{leak} of {expected} ({_ratio(leak, expected)})**",
        f"- False alarms on positive and negative items: **{alarms}** (precision {_ratio(hit, hit + alarms)})",
        f"- Public contact details redacted anyway: {len(result['public_redacted'])} of {result['items']['public']}",
        "",
        "| Type | Values | Hidden, right type | Leaked | False alarms |",
        "|---|---|---|---|---|",
    ]
    for kind, c in result["per_type"].items():
        lines.append(
            f"| {kind} | {c.get('expected', 0)} | {c.get('hit', 0)} ({_ratio(c.get('hit', 0), c.get('expected', 0))}) "
            f"| {c.get('leak', 0)} | {c.get('false_alarm', 0)} |"
        )
    lines += ["", "## Misses (the evidence behind the numbers)", ""]
    lines += [f"- `{m['id']}`: expected {m['expected']}; output `{m['output']}`" for m in result["misses"]] or ["None."]
    lines += ["", "## False alarms", ""]
    lines += [f"- `{f['id']}` ({f['kind']}): unexpected {f['unexpected']}" for f in result["false_alarms"]] or ["None."]
    lines += ["", "## Public details redacted", ""]
    lines += [f"- `{p['id']}`: {p['placeholders']}" for p in result["public_redacted"]] or ["None."]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gold", type=Path, default=GOLD_PATH)
    parser.add_argument("--doc", type=Path, default=DOC_PATH)
    parser.add_argument("--write-doc", action="store_true", help="rewrite the report document")
    parser.add_argument("--check", action="store_true", help="exit 1 if the report document is out of date")
    args = parser.parse_args(argv)

    text = report(evaluate(load_gold(args.gold)))
    if args.check:
        current = args.doc.read_text(encoding="utf-8") if args.doc.is_file() else ""
        if current != text:
            print(f"out of date (run python -m pipeline.eval_pii --write-doc): {args.doc}")
            return 1
        print("PII report is up to date")
        return 0
    if args.write_doc:
        args.doc.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {args.doc}")
        return 0
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
