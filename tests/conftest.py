from __future__ import annotations

import json
from pathlib import Path

import pytest

# Shared fakes come from mythings.testing (plain imports, no pytest_plugins:
# a top-level import alongside plugin registration would skip assertion
# rewriting). The aliased import re-exports the fixture — pytest registers it
# under the attribute name — and the wrapper below makes it autouse.
from mythings.ledger import Ledger, LedgerEntry
from mythings.testing import FakeGh
from mythings.testing import attended_env as _shared_attended_env  # noqa: F401


@pytest.fixture(autouse=True)
def _attended_env(request: pytest.FixtureRequest) -> None:
    # Default the suite to the attended path (a human is present). CI sets
    # GITHUB_ACTIONS=true, which otherwise collapses the tracking-issue-edit
    # ASK to DENY (fail-closed) and suppresses the edit — a real behavior the
    # suite must opt into deliberately, not inherit from the runner's env.
    request.getfixturevalue("_shared_attended_env")


def gh_tracking(body: str = "") -> FakeGh:
    # The gh boundary: tracking-issue view returns a body, edit records.
    return FakeGh({("issue", "view"): body, ("issue", "edit"): ""})


def write_manifest(tmp_path: Path, entries: list[dict]) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


def mentry(tool: str, repo: str, added: str, depends_on: list[str] | None = None) -> dict:
    return {
        "tool": tool,
        "repo": repo,
        "title": "x",
        "added": added,
        "depends_on": depends_on or [],
    }


def make_repo_root(tmp_path: Path, signals: dict[str, list[LedgerEntry]]) -> Path:
    root = tmp_path / "workspace"
    for repo, entries in signals.items():
        dev = root / repo / "dev-ledger"
        dev.mkdir(parents=True)
        ledger = Ledger(dev / "session.jsonl")
        for entry in entries:
            ledger.append(entry)
    return root


def build(repo: str, detail: str, ts: str) -> LedgerEntry:
    return LedgerEntry(tool="claude-code", kind="build", outcome="success", detail=detail, ts=ts)
