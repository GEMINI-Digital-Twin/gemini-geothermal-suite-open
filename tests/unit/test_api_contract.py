"""The table of ``.claude/docs/api.md`` lists every public name, its signature and no other."""

import ast
import enum
import inspect
import re

import pytest

import gemini as gm
from tests.fixtures import ROOT
from tests.fixtures.capture_public_api import METHODS, NAMESPACES

PAGE = ROOT / ".claude" / "docs" / "api.md"
SECTION = "## Names and signatures"
ROW = re.compile(r"^\| `(gm\.[^`]+)` \| (?:`([^`]*)`)? ?\| (\w+) \|$")
PATTERNS = {"gm.modules.<Equipment>": "modules", "gm.plants.<Plant class>": "plants"}
"""The catalogue rows: one row for the classes of a category, expanded by the registry."""
METHOD_CLASSES = ("Case", "Study", "Plant", "Module", "Engine", "Results")
"""The classes whose methods the snapshot pins and the table lists."""


def rows():
    """Return ``{name: (signature text or None, kind)}`` of the table of the page."""
    text = PAGE.read_text()
    assert SECTION in text, f"{SECTION!r} is missing from api.md"
    body = text.split(SECTION)[1].split("\n## ")[0]
    found = {}
    for line in body.splitlines():
        match = ROW.match(line)
        if match:
            assert match.group(1) not in found, f"{match.group(1)} is listed twice"
            found[match.group(1)] = (match.group(2), match.group(3))
    return found


def resolve(name):
    """Return the object a dotted public name reaches, or raise ``AttributeError``."""
    parts = name.split(".")[1:]
    value = gm
    for part in parts:
        value = getattr(value, part)
    return value


def text_of(default):
    """Return the source text of a default value, ``...`` when it has no expression form."""
    try:
        return ast.unparse(ast.parse(repr(default), mode="eval"))
    except SyntaxError:
        return "..."


def parameters_of(function):
    """Return ``[(name, kind, default text)]`` of a callable without ``self`` and ``cls``.

    A class that Python gives no signature (a subclass of ``dict`` or of ``Warning``) has ``None``.
    """
    try:
        found = inspect.signature(function).parameters.values()
    except ValueError:
        return None
    return [
        (item.name, item.kind.name, "" if item.default is item.empty else text_of(item.default))
        for item in found
        if item.name not in ("self", "cls")
    ]


def parameters_in(signature):
    """Return ``[(name, kind, default text)]`` of a signature written in the table."""
    tree = ast.parse(f"def f{signature}: pass").body[0].args
    found = [(item.arg, "POSITIONAL_ONLY", None) for item in tree.posonlyargs]
    found += [(item.arg, "POSITIONAL_OR_KEYWORD", None) for item in tree.args]
    defaults = [None] * (len(found) - len(tree.defaults)) + list(tree.defaults)
    found = [(*item[:2], default) for item, default in zip(found, defaults)]
    if tree.vararg:
        found.append((tree.vararg.arg, "VAR_POSITIONAL", None))
    for item, default in zip(tree.kwonlyargs, tree.kw_defaults):
        found.append((item.arg, "KEYWORD_ONLY", default))
    if tree.kwarg:
        found.append((tree.kwarg.arg, "VAR_KEYWORD", None))
    return [(n, k, "" if d is None else ast.unparse(d)) for n, k, d in found]


def public_names():
    """Return every name of ``gm.__all__`` and of each folder's ``__all__``, as ``gm.…``."""
    catalogue = set(gm.modules.names())
    names = [f"gm.{name}" for name in gm.__all__]
    for folder in sorted({"modules", "runtime", "errors", *NAMESPACES}):
        for name in getattr(gm, folder).__all__:
            if not (name in catalogue and folder in ("modules", "plants")):
                names.append(f"gm.{folder}.{name}")
    names += [f"gm.{cls}.{method}" for cls in METHOD_CLASSES for method in METHODS[cls]]
    return [name for name in names if not name.endswith(".__init__")]


def test_every_public_name_is_in_the_table():
    """A name of ``__all__`` or a pinned method that the table lacks fails the page."""
    listed = rows()
    assert [name for name in public_names() if name not in listed] == []


def test_every_name_in_the_table_exists():
    """A row that names nothing public (a removed or misspelt name) fails the page."""
    listed = rows()
    expected = set(public_names()) | set(PATTERNS)
    assert sorted(name for name in listed if name not in expected) == []
    for name in listed:
        if name not in PATTERNS:
            resolve(name)


@pytest.mark.parametrize("name", sorted(rows()))
def test_the_signature_of_a_row_is_the_signature_of_the_code(name):
    """Parameter names, kinds and defaults agree; a name with no signature has an empty cell."""
    if name in PATTERNS:
        return
    signature, kind = rows()[name]
    target = resolve(name)
    if inspect.isclass(target) and issubclass(target, enum.Enum):
        return
    if kind in ("class", "function", "method"):
        found = parameters_of(target)
        if found is None:
            assert signature is None, f"{name}: the code has no signature to compare"
            return
        assert signature is not None, f"{name}: the signature is missing"
        assert parameters_in(signature) == found, name
        return
    assert signature is None, f"{name}: a {kind} has no signature"


def test_a_catalogue_row_covers_exactly_the_registered_classes():
    """The classes a row stands for are the registry's, and each is exported by its folder."""
    for name, folder in PATTERNS.items():
        assert name in rows()
        exported = set(getattr(gm, folder).__all__) & set(gm.modules.names())
        assert exported, folder


def test_the_comparison_sees_a_name_a_kind_and_a_default():
    """A renamed argument, a keyword-only one and another default each differ from the code."""

    def function(plant, case, *, plan=None, mode="raise"):
        """Return nothing."""

    written = "(plant, case, *, plan=None, mode='raise')"
    assert parameters_in(written) == parameters_of(function)
    for other in (
        "(plant, case, *, plan=None, mode='record')",
        "(plant, case, plan=None, mode='raise')",
        "(plant, kase, *, plan=None, mode='raise')",
    ):
        assert parameters_in(other) != parameters_of(function)
