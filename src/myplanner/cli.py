from __future__ import annotations

import argparse
import json
from pathlib import Path

from mythings.engine import ClaudeCLIEngine, Engine
from mythings.ledger import Ledger

from myplanner.planner import Plan, Planner, Tracking

_ENGINE_NAMES = ("noop", "claude-cli")


def build_engine(name: str, *, model: str | None = None) -> Engine | None:
    if name == "claude-cli":
        return ClaudeCLIEngine(model=model)
    return None


def default_manifest_path() -> Path | None:
    # MyOrchestrator is a hard dependency; reuse its shipped manifest.json rather
    # than re-deriving the dependency graph. Resolve it from the installed package
    # if present, else the caller must pass --manifest.
    try:
        from importlib.resources import files

        return Path(str(files("myorchestrator").joinpath("manifest.json")))
    except (ImportError, ModuleNotFoundError):
        return None


def _render(plan: Plan, *, as_json: bool) -> str:
    if as_json:
        return json.dumps(
            {"plan": plan.items, "flags": plan.flags, "engine_used": plan.engine_used},
            separators=(",", ":"),
            sort_keys=True,
        )
    via = "engine" if plan.engine_used else "placeholder (no usable Engine reply)"
    lines = [f"plan ({via}):"]
    for i, item in enumerate(plan.items, 1):
        lines.append(f"  {i}. [{item['horizon']}] {item['item']} — {item['rationale']}")
    if plan.flags:
        lines.append("  flags: " + "; ".join(plan.flags))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="myplanner",
        description="Produce a priority-ordered, multi-item plan across the whole backlog.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    plan = sub.add_parser("plan", help="produce the recommended sequence")
    plan.add_argument("--org", default="MyThingsLab")
    plan.add_argument("--manifest", type=Path, default=default_manifest_path())
    plan.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd().parent,
        help="directory holding each repo as a subdir (defaults to the workspace root)",
    )
    plan.add_argument("--ledger", type=Path, default=Path(".mythings/ledger.jsonl"))
    plan.add_argument("--horizon", default="4w", help="planning horizon label (advisory)")
    plan.add_argument("--json", action="store_true")
    plan.add_argument("--tracking-repo", help='tracking issue repo, e.g. "MyThingsLab/core"')
    plan.add_argument("--tracking-issue", type=int, help="tracking issue number to update")
    plan.add_argument("--engine", choices=sorted(_ENGINE_NAMES), default="noop")
    plan.add_argument("--engine-model", help="model for --engine claude-cli")

    args = parser.parse_args(argv)
    if args.manifest is None:
        parser.error("could not locate myorchestrator's manifest.json; pass --manifest")

    tracking = (
        Tracking(repo=args.tracking_repo, issue=args.tracking_issue)
        if args.tracking_repo and args.tracking_issue
        else None
    )
    result = Planner(
        org=args.org,
        manifest_path=args.manifest,
        repo_root=args.repo_root,
        ledger=Ledger(args.ledger),
        engine=build_engine(args.engine, model=args.engine_model),
        tracking=tracking,
    ).plan()
    print(_render(result, as_json=args.json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
