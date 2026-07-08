from __future__ import annotations

from pathlib import Path

import pytest
from mythings.engine import EngineResult
from mythings.ledger import Ledger

from conftest import FakeGh, SpyEngine, build, make_repo_root, mentry, write_manifest
from myplanner.planner import Planner, Tracking

_GOOD_REPLY = EngineResult(
    text=(
        '{"plan": ['
        '{"item": "my-tester", "rationale": "no deps, unblocks coverage", "horizon": "next"},'
        '{"item": "my-reviewer", "rationale": "needs core diff first", "horizon": "soon"}],'
        ' "flags": ["pause new tools, close a safety gap first"]}'
    )
)


def test_happy_path_engine_called_once_plan_lands_in_ledger_and_issue(tmp_path: Path) -> None:
    manifest = write_manifest(
        tmp_path,
        [
            mentry("MyTester", "my-tester", "2026-06-01"),
            mentry("MyReviewer", "my-reviewer", "2026-06-02"),
        ],
    )
    repo_root = make_repo_root(
        tmp_path, {"my-guard": [build("my-guard", "shipped rule engine", "2026-07-01T00:00:00Z")]}
    )
    gh = FakeGh(body="# Fleet\n\n- [ ] close the secret-leak safety gap\n")
    engine = SpyEngine(_GOOD_REPLY)
    ledger = Ledger(tmp_path / "ledger.jsonl")

    plan = Planner(
        org="MyThingsLab",
        manifest_path=manifest,
        repo_root=repo_root,
        ledger=ledger,
        runner=gh,
        engine=engine,
        tracking=Tracking(repo="MyThingsLab/my-things-core", issue=1),
    ).plan()

    assert len(engine.calls) == 1
    assert plan.engine_used is True
    assert [i["item"] for i in plan.items] == ["my-tester", "my-reviewer"]
    assert plan.flags == ["pause new tools, close a safety gap first"]

    entry = ledger.read(kind="plan")[-1]
    assert entry.outcome == "success"
    assert entry.data["plan"] == plan.items
    assert entry.data["flags"] == plan.flags
    assert entry.detail == "plan: 2 items, 1 flags"

    edit = [c for c in gh.calls if c[:2] == ["issue", "edit"]][0]
    new_body = edit[edit.index("--body") + 1]
    assert "## Recommended sequence" in new_body
    assert "**my-tester** _(next)_" in new_body
    assert "**Flags:** pause new tools" in new_body


def test_unattended_ci_suppresses_public_issue_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # In CI (unattended) the tracking-issue-edit ASK collapses to DENY, so the
    # planner still computes and records the plan but must NOT edit the public
    # tracking issue — the harness's fail-closed stance on public content.
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    manifest = write_manifest(
        tmp_path,
        [
            mentry("MyTester", "my-tester", "2026-06-01"),
            mentry("MyReviewer", "my-reviewer", "2026-06-02"),
        ],
    )
    repo_root = make_repo_root(tmp_path, {})
    gh = FakeGh(body="# Fleet\n\n- [ ] close the secret-leak safety gap\n")
    ledger = Ledger(tmp_path / "ledger.jsonl")

    plan = Planner(
        org="MyThingsLab",
        manifest_path=manifest,
        repo_root=repo_root,
        ledger=ledger,
        runner=gh,
        engine=SpyEngine(_GOOD_REPLY),
        tracking=Tracking(repo="MyThingsLab/my-things-core", issue=1),
    ).plan()

    assert [i["item"] for i in plan.items] == ["my-tester", "my-reviewer"]  # plan still computed
    assert ledger.read(kind="plan")[-1].outcome == "success"  # still recorded
    assert not any(c[:2] == ["issue", "edit"] for c in gh.calls)  # fail-closed: no public edit


def test_open_items_parsed_from_tracking_issue(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path, [mentry("MyTester", "my-tester", "2026-06-01")])
    repo_root = make_repo_root(tmp_path, {})
    gh = FakeGh(body="# Fleet\n- [ ] decide the projects-module shape\n- [x] already done\n")
    engine = SpyEngine(_GOOD_REPLY)

    Planner(
        org="MyThingsLab",
        manifest_path=manifest,
        repo_root=repo_root,
        ledger=Ledger(tmp_path / "l.jsonl"),
        runner=gh,
        engine=engine,
        tracking=Tracking(repo="MyThingsLab/my-things-core", issue=1),
    ).plan()

    bundle = engine.calls[0].prompt
    assert "decide the projects-module shape" in bundle
    assert "already done" not in bundle  # checked items are not open


def test_empty_backlog_still_calls_engine(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path, [])
    repo_root = make_repo_root(tmp_path, {})
    engine = SpyEngine()  # NoopEngine-like empty reply
    ledger = Ledger(tmp_path / "ledger.jsonl")

    plan = Planner(
        org="MyThingsLab",
        manifest_path=manifest,
        repo_root=repo_root,
        ledger=ledger,
        runner=FakeGh(),
        engine=engine,
    ).plan()

    assert len(engine.calls) == 1  # called even with nothing to plan
    assert engine.calls[0].context["empty_backlog"] is True
    assert plan.engine_used is False  # empty reply => placeholder
    assert len(plan.items) == 1
    assert "placeholder" in plan.items[0]["rationale"]
    assert ledger.read(kind="plan")  # still recorded


def test_unusable_reply_degrades_to_placeholder(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path, [mentry("MyTester", "my-tester", "2026-06-01")])
    repo_root = make_repo_root(tmp_path, {})
    engine = SpyEngine(EngineResult(text="not json at all"))

    plan = Planner(
        org="MyThingsLab",
        manifest_path=manifest,
        repo_root=repo_root,
        ledger=Ledger(tmp_path / "l.jsonl"),
        runner=FakeGh(),
        engine=engine,
    ).plan()

    assert plan.engine_used is False
    assert plan.items[0]["item"] == "MyTester"  # placeholder cites a real ready tool


def test_no_tracking_means_no_issue_edit(tmp_path: Path) -> None:
    manifest = write_manifest(tmp_path, [mentry("MyTester", "my-tester", "2026-06-01")])
    gh = FakeGh()

    Planner(
        org="MyThingsLab",
        manifest_path=manifest,
        repo_root=make_repo_root(tmp_path, {}),
        ledger=Ledger(tmp_path / "l.jsonl"),
        runner=gh,
        engine=SpyEngine(_GOOD_REPLY),
    ).plan()

    assert gh.calls == []  # never touches an issue without --tracking-*
