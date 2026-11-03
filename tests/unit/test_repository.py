"""What the repository itself holds, apart from the package."""

import subprocess

import pytest

from tests.fixtures import ROOT


def _git(*arguments):
    return subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True, text=True)


def test_nothing_under_tmp_is_tracked():
    """``.tmp/`` holds worktrees and scratch files, which are ignored and never committed."""
    if _git("rev-parse", "--git-dir").returncode != 0:
        pytest.skip("not a git checkout")
    assert _git("ls-files", ".tmp").stdout == ""
    assert _git("check-ignore", "-q", ".tmp/any").returncode == 0
