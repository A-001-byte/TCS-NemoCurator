"""End-to-end test for the BFSI curator pipeline.

Runs the pipeline via the public API on isolated temporary directories, verifies
stage contracts, document-to-chunk unit transitions, stage-to-stage continuity,
JSONL structure, PII redaction (requiring the 'en_core_web_sm' spaCy model for
PERSON_NAME detection), and byte-for-byte run determinism.
"""

import json
from pathlib import Path

from pipeline import run
from pipeline.api import curate

SAMPLES = (
    "bank_of_baroda_kyc.pdf",
    "fiu_india_brochure.pdf",
    "rbi_kyc_fidcindia_aug2025.pdf",
)

EXPECTED_STAGES = [
    "extract",
    "clean_langid",
    "heal",
    "dedup",
    "quality_filter",
    "pii_redact",
    "output",
]

REQUIRED_STAGE_KEYS = {
    "stage",
    "docs_in",
    "docs_out",
    "removed",
    "reason_counts",
}


def test_end_to_end(tmp_path: Path):
    # 1. Setup isolated inputs in tmp_path
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    raw_data_dir = run.ROOT / "data" / "raw"

    for name in SAMPLES:
        src = raw_data_dir / name
        assert src.is_file(), f"Parity sample not found: {src}"
        (pdf_dir / name).write_bytes(src.read_bytes())

    # 2. Run isolated pipeline via public API (Run 1)
    out_dir1 = tmp_path / "run1_output"
    res1 = curate(pdf_dir, out_dir1, device="cpu")

    summary1 = res1.summary
    assert res1.device == "cpu"
    assert res1.output_path.is_file()
    assert res1.summary_path.is_file()
    # Unix line endings on every operating system, so the same input gives the same bytes (and hash) everywhere.
    for written in (res1.output_path, res1.summary_path):
        assert b"\r" not in written.read_bytes(), written.name

    # 3. Stage names and contract keys
    stages = summary1["stages"]
    actual_stages = [s["stage"] for s in stages]
    assert actual_stages == EXPECTED_STAGES, f"Unexpected stage sequence: {actual_stages}"

    stage_by_name = {}
    for s in stages:
        name = s["stage"]
        stage_by_name[name] = s
        missing = REQUIRED_STAGE_KEYS - set(s.keys())
        assert not missing, f"Stage {name} missing required contract keys: {missing}"
        assert s["docs_out"] == s["docs_in"] - s["removed"], (
            f"Stage {name}: docs_out ({s['docs_out']}) != docs_in ({s['docs_in']}) - removed ({s['removed']})"
        )

    # 4. Document-count continuity: extract -> clean_langid -> heal
    extract_stage = stage_by_name["extract"]
    clean_stage = stage_by_name["clean_langid"]
    heal_stage = stage_by_name["heal"]

    assert extract_stage["docs_in"] == len(SAMPLES)
    assert clean_stage["docs_in"] == extract_stage["docs_out"]
    assert heal_stage["docs_in"] == clean_stage["docs_out"]

    # 5. Document-to-chunk unit transition (heal -> dedup)
    # The first three stages process entire documents (unit = document).
    # Starting at dedup, the pipeline chunks each healed document into segments (unit = chunk).
    # Therefore, dedup.docs_in is a count of chunks, not documents.
    # For these three representative PDFs, chunk count strictly exceeds the document count.
    dedup_stage = stage_by_name["dedup"]
    assert dedup_stage["docs_in"] > heal_stage["docs_out"], (
        f"Expected chunk count in dedup ({dedup_stage['docs_in']}) to exceed "
        f"healed document count ({heal_stage['docs_out']})"
    )

    # 6. Chunk-count continuity: dedup -> quality_filter -> pii_redact -> output
    quality_stage = stage_by_name["quality_filter"]
    pii_stage = stage_by_name["pii_redact"]
    output_stage = stage_by_name["output"]

    assert quality_stage["docs_in"] == dedup_stage["docs_out"]
    assert pii_stage["docs_in"] == quality_stage["docs_out"]
    assert output_stage["docs_in"] == pii_stage["docs_out"]
    assert summary1["final_output_chunks"] == output_stage["docs_out"]
    assert output_stage["docs_out"] > 0

    # 7. Final JSONL structure and metadata
    jsonl_text1 = res1.output_path.read_text(encoding="utf-8")
    lines1 = [line for line in jsonl_text1.splitlines() if line.strip()]
    assert len(lines1) == summary1["final_output_chunks"]

    records = [json.loads(line) for line in lines1]
    for idx, rec in enumerate(records):
        assert "text" in rec and isinstance(rec["text"], str) and len(rec["text"]) > 0, (
            f"Record {idx} missing or empty text"
        )
        assert "metadata" in rec and isinstance(rec["metadata"], dict), f"Record {idx} missing metadata dict"
        meta = rec["metadata"]
        for key in ("chunk_id", "doc_id", "source_file", "pii_redacted"):
            assert key in meta, f"Record {idx} metadata missing key: {key}"
        assert isinstance(meta["pii_redacted"], bool)

    # 8. Exercise PII redaction: assert placeholders present, raw values absent
    all_curated_text = "\n".join(rec["text"] for rec in records)

    expected_placeholders = [
        "[REDACTED_SWIFT_BIC]",
        "[REDACTED_PINCODE]",
        "[REDACTED_EMAIL]",
        "[REDACTED_PERSON_NAME]",
    ]
    for placeholder in expected_placeholders:
        assert placeholder in all_curated_text, f"Expected placeholder {placeholder} not found in output"

    # Prerequisite check: Title-case person name redaction requires spaCy en_core_web_sm
    if not summary1.get("name_detection_available"):
        raise AssertionError(
            "Prerequisite missing: spaCy model 'en_core_web_sm' is not available. "
            "Install it inside the venv via 'python -m spacy download en_core_web_sm' "
            "to enable PERSON_NAME redaction."
        )

    # Specific chunk check for title-gated person name redaction
    c1 = next((r for r in records if r["metadata"]["chunk_id"] == "bank_of_baroda_kyc__1"), None)
    assert c1 is not None, "Expected chunk bank_of_baroda_kyc__1 not found"
    assert "[REDACTED_PERSON_NAME]" in c1["text"]
    raw_person_name = "Pankaj Mittal"
    assert raw_person_name not in c1["text"], "Verified person name was not redacted in chunk bank_of_baroda_kyc__1"

    # Global redaction check for other verified raw PII entities across curated output
    global_raw_pii = [
        "BARBINBBXXX",
        "390006",
        "390007",
        "feedbk@fiuindia.gov.in",
        "helpdesk@fiuindia.gov.in",
        "gm.oQs.ho@bankofbaroda.com",
    ]
    for raw_val in global_raw_pii:
        assert raw_val not in all_curated_text, "A verified input PII entity was not redacted in curated output"

    assert summary1["pii_entities_redacted"] > 0
    assert any(rec["metadata"]["pii_redacted"] for rec in records)

    # 9. Determinism: run isolated pipeline a second time on identical inputs
    out_dir2 = tmp_path / "run2_output"
    res2 = curate(pdf_dir, out_dir2, device="cpu")

    bytes1 = res1.output_path.read_bytes()
    bytes2 = res2.output_path.read_bytes()

    if bytes1 != bytes2:
        l1 = res1.output_path.read_text(encoding="utf-8").splitlines()
        l2 = res2.output_path.read_text(encoding="utf-8").splitlines()
        first_diff_idx = None
        meta1 = None
        meta2 = None
        for i, (line_a, line_b) in enumerate(zip(l1, l2)):
            if line_a != line_b:
                first_diff_idx = i
                try:
                    meta1 = json.loads(line_a).get("metadata", {})
                except Exception:
                    meta1 = "unparseable"
                try:
                    meta2 = json.loads(line_b).get("metadata", {})
                except Exception:
                    meta2 = "unparseable"
                break
        if first_diff_idx is None and len(l1) != len(l2):
            first_diff_idx = min(len(l1), len(l2))
        raise AssertionError(
            f"Curated JSONL outputs differ between identical runs: "
            f"bytes1={len(bytes1)}, bytes2={len(bytes2)}, "
            f"lines1={len(l1)}, lines2={len(l2)}, "
            f"first_differing_line={first_diff_idx}, "
            f"record1_metadata={meta1}, record2_metadata={meta2}"
        )

    assert bytes1 == bytes2, "Curated JSONL outputs are not byte-for-byte identical"


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        test_end_to_end(Path(temp_dir))
    print("ok: end-to-end test passed")
