"""Self-check for the GLiNER path, WITHOUT the model or the gliner package installed.

Run: python -m pipeline.test_pii_gliner
A stub stands in for the model so overlap resolution, the PERSON guard, the label
restriction and the lazy-import error are tested with synthetic spans.
"""
import sys

from pipeline import pii


class StubModel:
    """Returns canned (label, text, score) entities with offsets located in the window."""

    def __init__(self, entities):
        self.entities = entities

    def predict_entities(self, window_text, labels, threshold=0.0):
        out = []
        for label, text, score in self.entities:
            start = window_text.find(text)
            if start != -1:
                out.append({"label": label, "text": text, "start": start, "end": start + len(text), "score": score})
        return out


def redact_with(text, entities, **settings):
    saved = {k: getattr(pii, k) for k in settings} | {"_gliner_model": pii._gliner_model}
    try:
        for key, value in settings.items():
            setattr(pii, key, value)
        pii._gliner_model = StubModel(entities)
        counts = {}
        out, had = pii.redact_pii_gliner(text, counts, [], "t")
        return out, counts, had
    finally:
        for key, value in saved.items():
            setattr(pii, key, value)


def main():
    # --- Overlap resolution: higher score wins, then longer, then earlier -----------------
    span = lambda s, e, score: {"start": s, "end": e, "score": score}  # noqa: E731
    kept = pii._resolve_overlaps([span(0, 10, 0.5), span(5, 15, 0.9)])
    assert kept == [span(5, 15, 0.9)], "higher score wins"
    kept = pii._resolve_overlaps([span(0, 10, 0.7), span(5, 8, 0.7)])
    assert kept == [span(0, 10, 0.7)], "equal score: longer wins"
    kept = pii._resolve_overlaps([span(10, 20, 0.4), span(0, 10, 0.9), span(30, 35, 0.2)])
    assert kept == [span(0, 10, 0.9), span(10, 20, 0.4), span(30, 35, 0.2)], "touching spans both kept, sorted"
    assert pii._resolve_overlaps([]) == []

    # --- Overlapping spans of DIFFERENT labels no longer corrupt the text ---------------
    text = "Contact Mr. Anil Rao at anil.rao@bank.in or 9820320181 today"
    entities = [
        ("person", "Anil Rao", 0.95),
        ("email address", "anil.rao@bank.in", 0.99),
        ("phone number", "9820320181", 0.97),
        ("swift code", "Rao at anil.rao@bank.in", 0.40),  # overlaps the person AND the email
    ]
    out, counts, had = redact_with(text, entities)
    assert out == "Contact Mr. [REDACTED_PERSON_NAME] at [REDACTED_EMAIL] or [REDACTED_PHONE] today", out
    assert counts == {"PERSON_NAME": 1, "EMAIL": 1, "PHONE": 1} and had

    # --- PERSON guard: job titles are not names; the guard is switchable -----------------
    text = "the Managing Director signed the circular"
    entities = [("person", "Managing Director", 0.9)]
    out, counts, had = redact_with(text, entities)
    assert out == text and not had, "no title cue / name shape: left alone"
    out, counts, had = redact_with(text, entities, GLINER_PERSON_GUARD=False)
    assert "[REDACTED_PERSON_NAME]" in out, "guard off: GLiNER's own judgment"

    # --- Label restriction ---------------------------------------------------------------
    text = "Mr. Anil Rao phone 9820320181"
    entities = [("person", "Anil Rao", 0.9), ("phone number", "9820320181", 0.9)]
    out, counts, _ = redact_with(text, entities, GLINER_ENABLED_TYPES={"PHONE", "EMAIL"})
    assert counts == {"PHONE": 1} and "Anil Rao" in out

    # --- Lazy import and clear failure ---------------------------------------------------
    assert "gliner" not in sys.modules or sys.modules["gliner"] is None, "importing pii must not import gliner"
    saved_model, saved_module, saved_flag = pii._gliner_model, sys.modules.get("gliner"), pii.USE_GLINER_PII
    try:
        pii._gliner_model = None
        sys.modules["gliner"] = None  # makes `from gliner import GLiNER` raise ImportError
        try:
            pii._load_gliner()
        except RuntimeError as exc:
            assert "not installed" in str(exc) and "USE_GLINER_PII" in str(exc)
        else:
            raise AssertionError("missing gliner must raise, not fall back silently")
        pii.USE_GLINER_PII = True
        try:
            pii.main()
        except RuntimeError as exc:
            assert "not installed" in str(exc)
        else:
            raise AssertionError("main() with GLiNER on and gliner missing must fail loudly")
    finally:
        pii._gliner_model, pii.USE_GLINER_PII = saved_model, saved_flag
        if saved_module is None:
            sys.modules.pop("gliner", None)
        else:
            sys.modules["gliner"] = saved_module

    print("ok: GLiNER overlap resolution, person guard, label restriction, lazy import")


if __name__ == "__main__":
    main()
