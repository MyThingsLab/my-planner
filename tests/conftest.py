from __future__ import annotations

import json
from pathlib import Path

import pytest
from mythings.engine import EngineRequest, EngineResult
from mythings.ledger import Ledger, LedgerEntry


@pytest.fixture(autouse=True)
def _attended_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Default the suite to the attended path (a human is present). CI sets
    # GITHUB_ACTIONS=true, which otherwise collapses the tracking-issue-edit
    # ASK to DENY (fail-closed) and suppresses the edit — a real behavior the
    # suite must opt into deliberately, not inherit from the runner's env.
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


class SpyEngine:
    def __init__(self, result: EngineResult | None = None) -> None:
        self.calls: list[EngineRequest] = []
        self.result = result or EngineResult(text="", data={})

    def run(self, request: EngineRequest) -> EngineResult:
        self.calls.append(request)
        return self.result


class FakeGh:
    # Mocks the `gh` boundary: tracking-issue view returns a body, edit records.
    def __init__(self, body: str = "") -> None:
        self.body = body
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str]) -> str:
        self.calls.append(argv)
        if argv[:2] == ["issue", "view"]:
            return self.body
        if argv[:2] == ["issue", "edit"]:
            return ""
        raise AssertionError(f"unexpected gh call: {argv}")


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
