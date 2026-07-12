from __future__ import annotations

import json
from pathlib import Path

import pytest
from mythings.engine import ClaudeCLIEngine

from conftest import make_repo_root, mentry, write_manifest
from myplanner import cli
from myplanner.planner import Plan


def test_build_engine_claude_cli_returns_configured_engine() -> None:
    engine = cli.build_engine("claude-cli", model="opus")
    assert isinstance(engine, ClaudeCLIEngine)


def test_build_engine_noop_returns_none() -> None:
    assert cli.build_engine("noop") is None


def test_default_manifest_path_resolves_from_installed_mythings() -> None:
    path = cli.default_manifest_path()
    assert path is not None
    assert path.name == "tools_manifest.json"


def test_default_manifest_path_none_when_mythings_not_importable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "importlib.resources" or name.startswith("mythings"):
            raise ModuleNotFoundError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert cli.default_manifest_path() is None


def test_render_json_includes_plan_flags_and_engine_used() -> None:
    plan = Plan(
        items=[{"item": "my-tester", "rationale": "go", "horizon": "next"}],
        flags=["slow down"],
        engine_used=True,
    )
    out = cli._render(plan, as_json=True)
    parsed = json.loads(out)
    assert parsed == {
        "plan": plan.items,
        "flags": plan.flags,
        "engine_used": True,
    }


def test_render_text_placeholder_vs_engine_used() -> None:
    placeholder = Plan(items=[{"item": "x", "rationale": "r", "horizon": "next"}], flags=[])
    text = cli._render(placeholder, as_json=False)
    assert "placeholder (no usable Engine reply)" in text
    assert "1. [next] x — r" in text

    from_engine = Plan(
        items=[{"item": "y", "rationale": "r2", "horizon": "soon"}],
        flags=["pace it"],
        engine_used=True,
    )
    text2 = cli._render(from_engine, as_json=False)
    assert "plan (engine):" in text2
    assert "flags: pace it" in text2


def test_main_errors_when_manifest_cannot_be_located(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "default_manifest_path", lambda: None)
    with pytest.raises(SystemExit) as exc:
        cli.main(["plan"])
    assert exc.value.code == 2
    assert "could not locate mythings' tools_manifest.json" in capsys.readouterr().err


def test_main_runs_full_plan_and_prints_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = write_manifest(tmp_path, [mentry("MyTester", "my-tester", "2026-06-01")])
    repo_root = make_repo_root(tmp_path, {})
    ledger_path = tmp_path / "ledger.jsonl"

    rc = cli.main(
        [
            "plan",
            "--manifest",
            str(manifest),
            "--repo-root",
            str(repo_root),
            "--ledger",
            str(ledger_path),
        ]
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert "plan (placeholder (no usable Engine reply)):" in out
    assert "MyTester" in out
    assert ledger_path.exists()


def test_main_runs_full_plan_and_prints_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = write_manifest(tmp_path, [mentry("MyTester", "my-tester", "2026-06-01")])
    repo_root = make_repo_root(tmp_path, {})

    rc = cli.main(
        [
            "plan",
            "--manifest",
            str(manifest),
            "--repo-root",
            str(repo_root),
            "--ledger",
            str(tmp_path / "ledger.jsonl"),
            "--json",
        ]
    )

    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["engine_used"] is False
    assert parsed["plan"][0]["item"] == "MyTester"


def test_main_wires_tracking_repo_and_issue_into_planner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # CLI has no --runner injection point (by design: it's the real entrypoint),
    # so assert on how main() constructs the Planner rather than letting .plan()
    # run for real — with tracking set, that would shell out to the real `gh`.
    manifest = write_manifest(tmp_path, [mentry("MyTester", "my-tester", "2026-06-01")])
    repo_root = make_repo_root(tmp_path, {})
    captured: dict[str, object] = {}

    class SpyPlanner:
        def __init__(self, *args: object, **kwargs: object) -> None:
            captured.update(kwargs)

        def plan(self) -> Plan:
            return Plan(items=[], flags=[], engine_used=False)

    monkeypatch.setattr(cli, "Planner", SpyPlanner)

    rc = cli.main(
        [
            "plan",
            "--manifest",
            str(manifest),
            "--repo-root",
            str(repo_root),
            "--ledger",
            str(tmp_path / "ledger.jsonl"),
            "--tracking-repo",
            "MyThingsLab/my-things-core",
            "--tracking-issue",
            "1",
        ]
    )

    assert rc == 0
    tracking = captured["tracking"]
    assert tracking.repo == "MyThingsLab/my-things-core"
    assert tracking.issue == 1


def test_main_without_tracking_flags_builds_planner_with_no_tracking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = write_manifest(tmp_path, [mentry("MyTester", "my-tester", "2026-06-01")])
    repo_root = make_repo_root(tmp_path, {})
    captured: dict[str, object] = {}
    real_planner = cli.Planner

    def spy_planner(*args: object, **kwargs: object) -> object:
        captured.update(kwargs)
        return real_planner(*args, **kwargs)

    monkeypatch.setattr(cli, "Planner", spy_planner)

    cli.main(
        [
            "plan",
            "--manifest",
            str(manifest),
            "--repo-root",
            str(repo_root),
            "--ledger",
            str(tmp_path / "ledger.jsonl"),
        ]
    )

    assert captured["tracking"] is None
