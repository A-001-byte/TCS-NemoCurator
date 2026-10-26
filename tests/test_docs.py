"""The documentation points only at things that exist: markdown links, and file paths written in backticks."""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
# Written for the record, not maintained (docs/archive/README.md says so).
SKIPPED_FOLDERS = ("docs/archive/",)
# Paths documents mention on purpose although the repository does not hold them: the individual task files that were
# handed out separately (docs/README.md says so), and files other documents describe as generated or untracked.
NOT_IN_REPOSITORY = re.compile(r"(^|/)(0[0-9]_[A-Z_]+\.md|REPO-IMPROVEMENT-PROMPT\.md)$")
LINK = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)\)")
CODE_PATH = re.compile(
    r"`((?:pipeline|tests|scripts|dashboard|docs|\.github)/[\w./-]+\.(?:py|md|json|jsonl|txt|js|jsx|mjs|yml|toml))`"
)


def tracked_markdown() -> list:
    listing = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split("\n")
    names = [name for name in listing if name and not name.startswith(SKIPPED_FOLDERS)]
    return [ROOT / name for name in names if (ROOT / name).is_file()]


DOCUMENTS = tracked_markdown()


def ids(paths):
    return [str(path.relative_to(ROOT)).replace("\\", "/") for path in paths]


def test_the_documents_were_found():
    names = ids(DOCUMENTS)
    for expected in ("README.md", "SETUP.md", "STATUS.md", "docs/README.md", "docs/IMPROVEMENT_LOG.md"):
        assert expected in names


@pytest.mark.parametrize("document", DOCUMENTS, ids=ids(DOCUMENTS))
def test_every_relative_markdown_link_resolves(document):
    broken = []
    for target in LINK.findall(document.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path = target.split("#")[0]
        if path and not (document.parent / path).exists():
            broken.append(target)
    assert not broken, f"{document.name} links to missing files: {broken}"


@pytest.mark.parametrize("document", DOCUMENTS, ids=ids(DOCUMENTS))
def test_every_file_path_in_backticks_exists(document):
    missing = []
    for path in CODE_PATH.findall(document.read_text(encoding="utf-8")):
        if NOT_IN_REPOSITORY.search(path) or "*" in path:
            continue
        if not (ROOT / path).exists() and not (document.parent / path).exists():
            missing.append(path)
    assert not missing, f"{document.name} names files that do not exist: {sorted(set(missing))}"


def test_the_checker_itself_sees_a_broken_link(tmp_path):
    page = tmp_path / "page.md"
    page.write_text("[ok](page.md) [gone](nowhere.md) [web](https://example.com) [here](#top)", encoding="utf-8")
    targets = [t for t in LINK.findall(page.read_text(encoding="utf-8")) if not t.startswith(("http", "#"))]
    assert [t for t in targets if not (tmp_path / t).exists()] == ["nowhere.md"]
    assert CODE_PATH.findall("see `pipeline/api.py` and `data/raw/x.pdf`") == ["pipeline/api.py"]
