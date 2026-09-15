"""The claims a README makes about the repository itself, which the figure tests do not cover.

`tests/test_readme_claims.py` asserts every number derived from the synthetic data. It cannot see a
different class of statement: claims about the repository. Test counts, the example count, the
module table, and whether a draft placeholder was ever filled in are all assertions about this
repository rather than about an operation, so no data-derived test looks at them.

That gap has produced two defects, both of which reached the remote branch. A placeholder token was
published verbatim where a runtime figure belonged, and a runtime figure was published from an
estimate that the next measurement contradicted. Neither broke a test, because neither is a figure.
These tests close the part of the category that can be checked cheaply.

One figure is deliberately left out. Statement coverage needs a full instrumented run to verify, so
asserting it here would put minutes into the fast gate to protect a number that moves by a point.
It is the one repository claim not under test, and both READMEs say so.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDERS = ("TIMING_", "PLACEHOLDER", "TODO", "FIXME", "XXX", "lorem ipsum", "TBD")


def markdown_files() -> list[Path]:
    """Every documentation file, excluding anything git would not track."""
    return sorted(
        path
        for path in ROOT.rglob("*.md")
        if ".git" not in path.parts and "node_modules" not in path.parts
    )


def collected(marker: str) -> int:
    """Count the tests pytest collects under a marker expression, without running them."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "-m",
            marker,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    # Quiet collection prints one "path: count" line per file and no total, so the total is the
    # sum of those lines rather than a figure to be read off one.
    counts = re.findall(r"^\S+\.py:\s*(\d+)$", result.stdout, re.M)
    if not counts:
        pytest.fail(f"could not read collected counts from pytest output:\n{result.stdout[-2000:]}")
    return sum(int(count) for count in counts)


def test_no_placeholder_survives_into_the_documentation() -> None:
    """The exact defect that shipped: a draft marker published as if it were a figure."""
    offenders = []
    for path in markdown_files():
        text = path.read_text(encoding="utf-8")
        for token in PLACEHOLDERS:
            if token in text:
                offenders.append(f"{path.relative_to(ROOT)}: {token}")
    assert not offenders, "placeholder tokens left in documentation: " + "; ".join(offenders)


def test_the_readmes_quote_the_number_of_tests_that_exist() -> None:
    """Both language editions, because a count corrected in one and not the other is the same bug."""
    total = collected("not slow") + collected("slow")
    fast = collected("not slow")

    english = (ROOT / "README.md").read_text(encoding="utf-8")
    portuguese = (ROOT / "README.pt-BR.md").read_text(encoding="utf-8")

    quoted_total_en = re.search(r"\*\*(\d[\d,]*) tests,", english)
    quoted_fast_en = re.search(r"runs (\d[\d,]*) of them", english)
    quoted_total_pt = re.search(r"\*\*(\d[\d,]*) testes,", portuguese)
    # Anchored on the sentence rather than on the verb: a loose pattern matched "roda 3.10".
    quoted_fast_pt = re.search(r"`make check` roda (\d[\d,]*)", portuguese)

    for label, match in (
        ("English total", quoted_total_en),
        ("English fast", quoted_fast_en),
        ("Portuguese total", quoted_total_pt),
        ("Portuguese fast", quoted_fast_pt),
    ):
        assert match is not None, f"could not find the {label} test count in the README"

    assert int(quoted_total_en.group(1).replace(",", "")) == total
    assert int(quoted_fast_en.group(1).replace(",", "")) == fast
    assert int(quoted_total_pt.group(1).replace(",", "")) == total
    assert int(quoted_fast_pt.group(1).replace(",", "")) == fast


def test_the_module_table_lists_every_module_and_no_others() -> None:
    """A module added without a table row is invisible; a row without a module is a dead link."""
    packages = {path.parent.name for path in (ROOT / "src" / "oplab").glob("*/__init__.py")}
    for readme in ("README.md", "README.pt-BR.md"):
        text = (ROOT / readme).read_text(encoding="utf-8")
        listed = set(re.findall(r"^\| `oplab\.(\w+)` \|", text, re.M))
        assert listed == packages, f"{readme}: table {sorted(listed)} vs package {sorted(packages)}"


def test_every_module_readme_is_bilingual() -> None:
    """The multi-market decision is a convention, so it is enforced rather than remembered."""
    for path in sorted((ROOT / "src" / "oplab").glob("*/README.md")):
        text = path.read_text(encoding="utf-8")
        assert "## Português" in text, f"{path.relative_to(ROOT)} has no Portuguese section"
        assert text.lstrip().startswith("#"), f"{path.relative_to(ROOT)} does not open with a title"


def test_both_root_readmes_document_the_same_findings() -> None:
    """A finding added to one edition and not the other is the commonest bilingual drift."""
    english = re.findall(r"^### (\d+)\.", (ROOT / "README.md").read_text(encoding="utf-8"), re.M)
    portuguese = re.findall(
        r"^### (\d+)\.", (ROOT / "README.pt-BR.md").read_text(encoding="utf-8"), re.M
    )
    assert english == portuguese
    # Numbered from one, with no gaps and no repeats.
    assert [int(number) for number in english] == list(range(1, len(english) + 1))


def test_every_example_script_is_referenced_by_a_module_readme_or_the_root() -> None:
    """An example nobody links is an example nobody runs."""
    scripts = sorted(path.name for path in (ROOT / "examples").glob("*.py"))
    assert scripts, "no example scripts found"

    linked = set()
    for path in markdown_files():
        text = path.read_text(encoding="utf-8")
        linked.update(re.findall(r"examples/([\w.]+\.py)", text))

    missing = [name for name in scripts if name not in linked]
    assert not missing, f"example scripts linked from no documentation: {missing}"
