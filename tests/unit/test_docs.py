"""Every ``python`` snippet of ``.claude/docs/`` runs: a page that shows code shows code that works.

A snippet of a page runs in the namespace of the snippets before it, as a reader follows the page,
from the root of the repository. A snippet that is only illustrative is rewritten to run or fenced
as ``text``; nothing is skipped silently. A page of many snippets is cut into runs of ``CHUNK``
snippets, each a test of its own under the CPU budget of a fast test; a page whose snippets depend
on one another across a cut fails on the cut, so it is kept within one run.
"""

import re

import pytest

from tests.fixtures import ROOT

DOCS = ROOT / ".claude" / "docs"
FENCE = re.compile(r"^```python\n(.*?)^```", re.MULTILINE | re.DOTALL)


def snippets(path):
    """Return ``[(line number, code)]`` of the ``python`` fences of a page."""
    text = path.read_text()
    return [
        (text.count("\n", 0, found.start()) + 2, found.group(1)) for found in FENCE.finditer(text)
    ]


CHUNK = 12
"""The most snippets of a page that run in one test."""
ONE_BY_ONE = ("engine.md",)
"""The pages whose snippets run whole streams of rows, each a test of its own."""


def runs():
    """Return ``[(page, first, last)]``: the snippets ``first`` to ``last`` (excluded) of a page."""
    found = []
    for path in sorted(DOCS.glob("*.md")):
        count, size = len(snippets(path)), 1 if path.name in ONE_BY_ONE else CHUNK
        found += [(path.name, start, min(start + size, count)) for start in range(0, count, size)]
    return found


PAGES = sorted({page for page, _, _ in runs()})


def test_the_pages_with_snippets_are_found():
    """The collector sees the pages that show code, and ignores the others."""
    assert {"api.md", "equipment.md", "plants.md"} <= set(PAGES)
    assert "glossary.md" not in PAGES


@pytest.mark.parametrize(("page", "first", "last"), runs(), ids=lambda v: str(v))
def test_every_snippet_of_a_page_runs(page, first, last, monkeypatch):
    """The snippets of one run of a page run in order in one namespace and raise nothing."""
    monkeypatch.chdir(ROOT)
    namespace = {"__name__": "__docs__"}
    for line, code in snippets(DOCS / page)[first:last]:
        exec(compile("\n" * (line - 1) + code, f"{page}", "exec"), namespace)
