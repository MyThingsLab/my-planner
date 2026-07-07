from __future__ import annotations

from myplanner.context import PlanContext, truncate
from myplanner.planner import Plan, render_section, upsert_section


def test_truncate_trims_oldest_velocity_first_but_keeps_bundle_present() -> None:
    ctx = PlanContext(
        manifest=[
            {"tool": "MyTester", "repo": "my-tester", "title": "t", "added": "", "depends_on": []}
        ],
        open_items=["gap one", "gap two"],
        velocity=[
            {"repo": "r", "kind": "build", "detail": f"entry {i}", "ts": f"2026-07-{i:02d}"}
            for i in range(1, 21)
        ],
    )
    trimmed = truncate(ctx, budget=400)

    assert len(trimmed.velocity) < 20  # velocity trimmed
    assert trimmed.velocity[-1]["ts"] == "2026-07-20"  # newest kept, oldest dropped
    assert trimmed.manifest  # never trimmed to empty


def test_upsert_appends_when_absent_then_replaces_in_place() -> None:
    plan = Plan(
        items=[{"item": "my-tester", "rationale": "go", "horizon": "next"}], flags=["slow down"]
    )
    section = render_section(plan)

    appended = upsert_section("# Fleet tracking\n\n- [ ] a task\n", section)
    assert "## Recommended sequence" in appended
    assert appended.count("## Recommended sequence") == 1

    plan2 = Plan(items=[{"item": "my-reviewer", "rationale": "next up", "horizon": "next"}])
    replaced = upsert_section(appended, render_section(plan2))
    assert replaced.count("## Recommended sequence") == 1  # replaced, not duplicated
    assert "my-reviewer" in replaced
    assert "my-tester" not in replaced


def test_upsert_preserves_following_section() -> None:
    body = "## Recommended sequence\n\n1. old\n\n## Other section\n\nkeep me\n"
    plan = Plan(items=[{"item": "my-tester", "rationale": "go", "horizon": "next"}])

    out = upsert_section(body, render_section(plan))

    assert "## Other section" in out
    assert "keep me" in out
    assert "old" not in out
