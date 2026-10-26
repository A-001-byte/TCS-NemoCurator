"""The PII evaluator: the gold set is well formed, the scoring is right, and the published report is current."""

import json
from collections import Counter

import pytest

from pipeline import eval_pii


@pytest.fixture(scope="module")
def gold():
    return eval_pii.load_gold()


def perfect_redactor(items):
    """Hides every gold value behind a placeholder of its own type, and nothing else."""
    by_text = {item["text"]: item for item in items}

    def redact(text):
        redacted, placeholders = text, Counter()
        for kind, value in by_text[text]["pii"]:
            redacted = redacted.replace(value, f"[REDACTED_{kind}]")
            placeholders[kind] += 1
        return redacted, placeholders

    return redact


def test_the_gold_set_is_well_formed(gold):
    kinds = Counter(item["kind"] for item in gold)
    assert kinds["positive"] >= 40 and kinds["negative"] >= 10 and kinds["public"] >= 1
    assert {kind for item in gold for kind, _ in item["pii"]} == set(eval_pii.TYPES)
    assert all(item["pii"] == [] for item in gold if item["kind"] != "positive")


def test_a_perfect_redactor_scores_full_recall_and_no_false_alarms(gold):
    result = eval_pii.evaluate(gold, perfect_redactor(gold))
    totals = result["totals"]
    assert totals["hit"] == totals["expected"] and totals.get("leak", 0) == 0 and totals.get("false_alarm", 0) == 0
    assert result["misses"] == [] and result["false_alarms"] == []


def test_a_redactor_that_does_nothing_leaks_every_value(gold):
    result = eval_pii.evaluate(gold, lambda text: (text, Counter()))
    totals = result["totals"]
    assert totals.get("hit", 0) == 0 and totals["leak"] == totals["expected"]
    assert len(result["misses"]) == sum(1 for item in gold if item["pii"])


def test_a_placeholder_of_the_wrong_type_is_not_a_hit_and_is_a_false_alarm(gold):
    item = next(i for i in gold if i["id"] == "pan-1")
    value = item["pii"][0][1]
    result = eval_pii.evaluate([item], lambda text: (text.replace(value, "[REDACTED_EMAIL]"), Counter({"EMAIL": 1})))
    assert result["per_type"]["PAN"]["hit"] == 0 and result["per_type"]["PAN"].get("leak", 0) == 0
    assert result["per_type"]["EMAIL"]["false_alarm"] == 1


def test_a_placeholder_on_a_negative_item_is_a_false_alarm(gold):
    item = next(i for i in gold if i["kind"] == "negative")
    result = eval_pii.evaluate([item], lambda text: (text, Counter({"PHONE": 1})))
    assert result["totals"]["false_alarm"] == 1 and result["false_alarms"][0]["id"] == item["id"]


def test_public_items_are_scored_apart_from_false_alarms(gold):
    item = next(i for i in gold if i["kind"] == "public")
    result = eval_pii.evaluate([item], lambda text: (text, Counter({"EMAIL": 2})))
    assert result["public_redacted"] == [{"id": item["id"], "placeholders": {"EMAIL": 2}}]
    assert result["totals"].get("false_alarm", 0) == 0


@pytest.mark.parametrize(
    "item, message",
    [
        ({"id": "x", "kind": "positive", "text": "a", "pii": [["PAN", "b"]]}, "not in the text"),
        ({"id": "x", "kind": "positive", "text": "a", "pii": [["NOPE", "a"]]}, "unknown type"),
        ({"id": "x", "kind": "odd", "text": "a", "pii": []}, "unknown kind"),
    ],
)
def test_a_malformed_gold_file_is_refused(tmp_path, item, message):
    path = tmp_path / "gold.jsonl"
    path.write_text(json.dumps(item) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        eval_pii.load_gold(path)


def test_duplicate_ids_are_refused(tmp_path):
    path = tmp_path / "gold.jsonl"
    line = json.dumps({"id": "x", "kind": "negative", "text": "a", "pii": []})
    path.write_text(f"{line}\n{line}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        eval_pii.load_gold(path)


def test_the_published_report_matches_the_real_stage():
    # Fails when a PII rule changed and `python -m pipeline.eval_pii --write-doc` was not run.
    assert eval_pii.main(["--check"]) == 0
