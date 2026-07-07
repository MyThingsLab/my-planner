from __future__ import annotations

import json
from pathlib import Path

from mythings._devledger import read_all
from mythings.github import Runner

# Velocity signal: the fleet's recent build/decision/ship cadence, read from every
# repo's dev-ledger (the same non-opt-in fleet-wide scope MyOrchestrator uses —
# this tool's whole purpose is the fleet view).
VELOCITY_KINDS = ("decision", "ship", "build")


def read_manifest(path: str | Path) -> list[dict]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    # Keep only what a plan needs; unbuilt tools are the planning surface.
    return [
        {
            "tool": obj["tool"],
            "repo": obj["repo"],
            "title": obj.get("title", ""),
            "added": obj.get("added", ""),
            "depends_on": list(obj.get("depends_on", [])),
        }
        for obj in raw
    ]


def read_velocity(repo_root: str | Path, repos: list[str], *, limit: int) -> list[dict]:
    root = Path(repo_root)
    entries = []
    for repo in repos:
        repo_path = root / repo
        if not (repo_path / "dev-ledger").is_dir():
            continue
        for e in read_all(root=repo_path):
            if e.kind in VELOCITY_KINDS:
                entries.append({"repo": repo, "kind": e.kind, "detail": e.detail, "ts": e.ts})
    entries.sort(key=lambda e: e["ts"])
    return entries[-limit:]  # most recent N across the fleet


def read_open_items(runner: Runner, *, repo: str, issue: int) -> list[str]:
    # Open decisions + safety gaps, parsed from the org-wide tracking issue: every
    # unchecked checklist line is an open item. This is the fallback that keeps
    # MyPlanner buildable without MyProjector's synced board.
    body = runner(
        ["issue", "view", str(issue), "--repo", repo, "--json", "body", "-q", ".body"]
    )
    out = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("- [ ]") or stripped.startswith("* [ ]"):
            out.append(stripped[5:].strip())
    return out
