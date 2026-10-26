"""The packaging metadata, the requirements files and the code's real imports must agree."""

import ast
import re
import sys
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

import pipeline

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

# import name -> distribution name, for the third-party modules the code uses
DISTRIBUTION = {
    "datasketch": "datasketch",
    "langdetect": "langdetect",
    "pdfplumber": "pdfplumber",
    "spacy": "spacy",
    "tiktoken": "tiktoken",
    "torch": "torch",
    "transformers": "transformers",
    "gliner": "gliner",
    "huggingface_hub": "huggingface-hub",
    "nemo_curator": "nemo-curator",
}
CORE = {"datasketch", "langdetect", "pdfplumber", "spacy", "tiktoken"}
OPTIONAL_ONLY = {"torch", "transformers", "gliner", "huggingface_hub", "nemo_curator"}
NEEDED_AT_IMPORT_TIME_BY_A_TOOL_SCRIPT = {"nemo_compare.py"}  # runs only on the NeMo VM


def requirement_lines(name: str) -> list:
    """The requirement specs of a requirements file (comments, blank lines and options dropped)."""
    out = []
    for line in (ROOT / name).read_text(encoding="utf-8").splitlines():
        line = line.split(" #")[0].strip()
        if line and not line.startswith(("#", "-r", "--")):
            out.append(Requirement(line))
    return out


def pins(name: str) -> dict:
    """{distribution name: pinned version or URL} for a requirements file."""
    result = {}
    for requirement in requirement_lines(name):
        specs = list(requirement.specifier)
        result[requirement.name.lower().replace("_", "-")] = requirement.url or (specs[0].version if specs else None)
    return result


def test_the_version_is_valid_and_comes_from_the_package():
    assert "version" in PYPROJECT["project"]["dynamic"]
    assert Version(pipeline.__version__)


def test_python_version_matches_what_we_test_on():
    assert PYPROJECT["project"]["requires-python"] == ">=3.11"
    assert sys.version_info >= (3, 11)


def test_every_core_dependency_is_pinned_in_requirements_inside_its_declared_range():
    declared = [Requirement(spec) for spec in PYPROJECT["project"]["dependencies"]]
    pinned = pins("requirements.txt")
    assert declared, "pyproject must declare the core dependencies (pip install . must be turnkey)"
    for requirement in declared:
        key = requirement.name.lower().replace("_", "-")
        assert key in pinned, f"{requirement.name} is declared but not pinned in requirements.txt"
        if requirement.url:
            assert pinned[key] == requirement.url
        else:
            assert Version(pinned[key]) in requirement.specifier, (
                f"{key}=={pinned[key]} is outside {requirement.specifier}"
            )


def test_pyproject_declares_every_core_package_the_code_imports():
    """`pip install .` must give a package that imports: nothing the code needs may be missing from pyproject."""
    declared = {Requirement(spec).name.lower().replace("_", "-") for spec in PYPROJECT["project"]["dependencies"]}
    for module in sorted(CORE):
        assert DISTRIBUTION[module] in declared, (
            f"{module} is imported by the code but {DISTRIBUTION[module]} is not in pyproject"
        )


@pytest.mark.parametrize(
    "extra,file", [("ml", "requirements-ml.txt"), ("nemo", "requirements-nemo.txt"), ("dev", "requirements-dev.txt")]
)
def test_every_extra_matches_its_requirements_file(extra, file):
    pinned = pins(file)
    for spec in PYPROJECT["project"]["optional-dependencies"][extra]:
        requirement = Requirement(spec)
        key = requirement.name.lower().replace("_", "-")
        assert key in pinned, f"{key} is in the {extra} extra but not in {file}"
        assert Version(pinned[key]) in requirement.specifier, f"{key}=={pinned[key]} is outside {requirement.specifier}"


def test_the_core_install_does_not_pull_in_the_heavy_optional_packages():
    core = set(pins("requirements.txt"))
    assert not core & {"torch", "transformers", "gliner", "nemo-curator", "cudf-cu12"}
    declared = {Requirement(spec).name.lower() for spec in PYPROJECT["project"]["dependencies"]}
    assert not declared & {"torch", "transformers", "gliner", "nemo-curator"}


def test_the_optional_files_build_on_the_core_file():
    for name in ("requirements-dev.txt", "requirements-ml.txt", "requirements-nemo.txt"):
        assert "-r requirements.txt" in (ROOT / name).read_text(encoding="utf-8"), name
    assert "-r requirements-ml.txt" in (ROOT / "requirements-gpu.txt").read_text(encoding="utf-8")


def third_party(tree: ast.Module, top_level_only: bool) -> set:
    nodes = tree.body if top_level_only else list(ast.walk(tree))
    modules = set()
    for node in nodes:
        if isinstance(node, ast.Import):
            modules |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module.split(".")[0])
    return {m for m in modules if m not in sys.stdlib_module_names and m != "pipeline"}


@pytest.mark.parametrize("path", sorted((ROOT / "pipeline").glob("*.py")), ids=lambda p: p.name)
def test_importing_a_pipeline_module_needs_only_the_core_install(path):
    """A top-level `import torch` would make `pip install .` unusable. Lazy imports inside a function are fine."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = third_party(tree, top_level_only=True)
    if path.name in NEEDED_AT_IMPORT_TIME_BY_A_TOOL_SCRIPT:
        imported -= OPTIONAL_ONLY
    assert imported <= CORE, f"{path.name} imports {sorted(imported - CORE)} at module level, outside the core install"


def test_every_third_party_module_the_code_uses_is_declared_somewhere():
    used = set()
    for path in (ROOT / "pipeline").glob("*.py"):
        used |= third_party(ast.parse(path.read_text(encoding="utf-8")), top_level_only=False)
    declared = set()
    for name in ("requirements.txt", "requirements-ml.txt", "requirements-nemo.txt"):
        declared |= set(pins(name))
    transitive = {"huggingface-hub"}  # installed by transformers
    for module in used:
        distribution = DISTRIBUTION.get(module)
        assert distribution, f"unknown third-party import {module!r}: add it to DISTRIBUTION and a requirements file"
        assert distribution in declared | transitive, (
            f"{module} is imported but {distribution} is in no requirements file"
        )


def test_the_requirement_files_have_no_duplicate_or_unpinned_entries():
    for name in (
        "requirements.txt",
        "requirements-dev.txt",
        "requirements-ml.txt",
        "requirements-nemo.txt",
        "requirements-gpu.txt",
    ):
        entries = requirement_lines(name)
        names = [e.name.lower() for e in entries]
        assert len(names) == len(set(names)), f"duplicate entry in {name}"
        for entry in entries:
            assert entry.url or re.search(r"==", str(entry.specifier)), f"{entry.name} in {name} is not pinned exactly"
