"""Write pipeline/doc_type_families.json: groups of near-copy documents (one policy in three
years, one RBI Direction re-hosted by two sites). The document-type evaluation holds a whole
group out together, otherwise a copy of the test document sits in the training set.

Run: python -m pipeline.doctype_families      (needs data/healed from a pipeline run)
"""
import json
from pathlib import Path

from pipeline.changelog import find_families

ROOT = Path(__file__).resolve().parent.parent
HEALED_DIR = ROOT / "data" / "healed"
OUT_PATH = Path(__file__).with_name("doc_type_families.json")


def load_texts(healed_dir: Path = HEALED_DIR) -> dict:
    """{source_file: text} for every healed document record (skips the report files)."""
    texts = {}
    for path in sorted(healed_dir.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(record, dict) and "text" in record and "source_file" in record:
            texts[record["source_file"]] = record["text"]
    return texts


def main():
    texts = load_texts()
    families = sorted(sorted(family) for family in find_families(texts))
    OUT_PATH.write_text(json.dumps({"families": families}, indent=2) + "\n", encoding="utf-8")
    print(f"{len(texts)} documents, {len(families)} near-copy families -> {OUT_PATH.name}")


if __name__ == "__main__":
    main()
