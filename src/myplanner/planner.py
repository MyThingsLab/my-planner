from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path

from mythings.engine import Engine, EngineRequest, NoopEngine
from mythings.github import Runner, _gh
from mythings.isolation import in_github_actions
from mythings.ledger import Ledger
from mythings.policy import ALLOW, Action, Decision, Policy, PolicyResult

from myplanner.context import PlanContext, truncate
from myplanner.sources import read_manifest, read_open_items, read_velocity

HORIZONS = ("next", "soon", "later")
SECTION_HEADER = "## Recommended sequence"

_ENGINE_SYSTEM = (
    "You are planning the build order for a fleet of small tools. Given the "
    "unbuilt-tools dependency graph, the open decisions/safety gaps, and recent "
    "activity, produce a priority-ordered plan and any pacing flags. Reply with "
    "only a JSON object: "
    '{"plan": [{"item": "<name>", "rationale": "<one sentence>", '
    '"horizon": "next|soon|later"}], "flags": ["<pacing note>"]}, nothing else.'
)


class DefaultPolicy:
    # Editing the org-wide tracking issue is public-content mutation: ASK by
    # default, the same classification MyProjector gives that action kind.
    def evaluate(self, action: Action) -> PolicyResult:
        if action.kind == "tracking-issue-edit":
            return PolicyResult(Decision.ASK, reason="edits public content", rule="public-content")
        return ALLOW


@dataclass(frozen=True)
class Tracking:
    repo: str  # "owner/repo"
    issue: int


@dataclass
class Plan:
    items: list[dict] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    engine_used: bool = False


class Planner:
    def __init__(
        self,
        *,
        org: str,
        manifest_path: str | Path,
        repo_root: str | Path,
        ledger: Ledger,
        runner: Runner = _gh,
        engine: Engine | None = None,
        policy: Policy | None = None,
        tracking: Tracking | None = None,
        velocity_limit: int = 50,
    ) -> None:
        self.org = org
        self.manifest_path = Path(manifest_path)
        self.repo_root = Path(repo_root)
        self.ledger = ledger
        self.runner = runner
        self.engine: Engine = engine or NoopEngine()
        self.policy: Policy = policy or DefaultPolicy()
        self.tracking = tracking
        self.velocity_limit = velocity_limit

    def plan(self) -> Plan:
        ctx = self._assemble()
        plan = self._ask_engine(ctx)
        self._record(plan)
        if self.tracking is not None:
            self._update_tracking(plan)
        return plan

    def _assemble(self) -> PlanContext:
        manifest = read_manifest(self.manifest_path)
        repos = sorted({t["repo"] for t in manifest} | set(self._built_repos()))
        velocity = read_velocity(self.repo_root, repos, limit=self.velocity_limit)
        open_items: list[str] = []
        if self.tracking is not None:
            open_items = read_open_items(
                self.runner, repo=self.tracking.repo, issue=self.tracking.issue
            )
        return truncate(PlanContext(manifest=manifest, open_items=open_items, velocity=velocity))

    def _built_repos(self) -> list[str]:
        # Any sibling dir with a dev-ledger is a real repo whose activity counts.
        if not self.repo_root.is_dir():
            return []
        return [p.name for p in self.repo_root.iterdir() if (p / "dev-ledger").is_dir()]

    def _ask_engine(self, ctx: PlanContext) -> Plan:
        # Always call the Engine, even on an empty backlog — "things look calm" is
        # still a recorded judgment.
        result = self.engine.run(
            EngineRequest(
                prompt=json.dumps(ctx.to_bundle(), separators=(",", ":"), sort_keys=True),
                system=_ENGINE_SYSTEM,
                context={"empty_backlog": ctx.is_empty},
            )
        )
        parsed = _parse_plan(result.text)
        if parsed is None:
            # NoopEngine / unusable reply: an explicit placeholder, not a real plan.
            return Plan(
                items=[
                    {
                        "item": _placeholder_item(ctx),
                        "rationale": "Engine gave no usable plan — placeholder, not advice",
                        "horizon": "next",
                    }
                ],
                flags=[],
                engine_used=False,
            )
        items, flags = parsed
        return Plan(items=items, flags=flags, engine_used=True)

    def _record(self, plan: Plan) -> None:
        self.ledger.record(
            tool="myplanner",
            kind="plan",
            outcome="success",
            detail=f"plan: {len(plan.items)} items, {len(plan.flags)} flags",
            plan=plan.items,
            flags=plan.flags,
        )

    def _update_tracking(self, plan: Plan) -> None:
        body = self.runner(
            ["issue", "view", str(self.tracking.issue), "--repo", self.tracking.repo,
             "--json", "body", "-q", ".body"]
        )
        new_body = upsert_section(body, render_section(plan))
        if new_body == body:
            return
        argv = ["issue", "edit", str(self.tracking.issue), "--repo", self.tracking.repo,
                "--body", new_body]
        action = Action(
            kind="tracking-issue-edit",
            payload={"repo": self.tracking.repo, "issue": self.tracking.issue,
                     "command": "gh " + shlex.join(argv)},
        )
        decision = self.policy.evaluate(action).under(unattended=in_github_actions())
        # Running `myplanner plan --tracking-*` is the explicit human opt-in that
        # satisfies the ASK tier — but only when attended; CI still DENYs.
        if decision is Decision.ALLOW or (decision is Decision.ASK and not in_github_actions()):
            self.runner(argv)


def _parse_plan(text: str) -> tuple[list[dict], list[str]] | None:
    try:
        obj = json.loads(text) if text else {}
    except json.JSONDecodeError:
        return None
    plan = obj.get("plan")
    if not isinstance(plan, list) or not plan:
        return None
    clean = []
    for it in plan:
        if not isinstance(it, dict):
            return None
        item, horizon = it.get("item"), it.get("horizon")
        if not isinstance(item, str) or horizon not in HORIZONS:
            return None
        clean.append({"item": item, "rationale": str(it.get("rationale", "")), "horizon": horizon})
    raw_flags = obj.get("flags", [])
    flags = [str(f) for f in raw_flags if isinstance(f, str)] if isinstance(raw_flags, list) else []
    return clean, flags


def _placeholder_item(ctx: PlanContext) -> str:
    return ctx.manifest[0]["tool"] if ctx.manifest else "review the backlog"


def render_section(plan: Plan) -> str:
    lines = [SECTION_HEADER, ""]
    for i, item in enumerate(plan.items, 1):
        lines.append(f"{i}. **{item['item']}** _({item['horizon']})_ — {item['rationale']}")
    if plan.flags:
        lines.append("")
        lines.append("**Flags:** " + "; ".join(plan.flags))
    return "\n".join(lines)


_SECTION_RE = re.compile(
    rf"^{re.escape(SECTION_HEADER)}\s*$.*?(?=^## |\Z)", re.MULTILINE | re.DOTALL
)


def upsert_section(body: str, section: str) -> str:
    # Replace an existing "## Recommended sequence" block (up to the next "## " or
    # end), else append it — never a second competing section.
    block = section.rstrip() + "\n"
    if _SECTION_RE.search(body):
        return _SECTION_RE.sub(block, body, count=1).rstrip() + "\n"
    sep = "" if body.endswith("\n\n") or not body else ("\n" if body.endswith("\n") else "\n\n")
    return body + sep + block
