from __future__ import annotations

from myplanner.context import PlanContext, truncate
from myplanner.planner import Plan, _parse_plan, render_section, upsert_section


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


def test_truncate_never_trims_the_last_item_of_any_list() -> None:
    # Each _trim_* helper refuses once its list is down to a single entry, so an
    # over-budget bundle still leaves one velocity/open-item/manifest entry
    # present rather than trimming everything away.
    ctx = PlanContext(
        manifest=[
            {"tool": "MyTester", "repo": "my-tester", "title": "t", "added": "", "depends_on": []}
        ],
        open_items=["only gap"],
        velocity=[{"repo": "r", "kind": "build", "detail": "only entry", "ts": "2026-07-01"}],
    )

    trimmed = truncate(ctx, budget=1)  # impossibly tight: every trim step maxes out

    assert trimmed.velocity == ctx.velocity
    assert trimmed.open_items == ctx.open_items
    assert trimmed.manifest == ctx.manifest


def test_truncate_trims_open_items_then_manifest_once_velocity_is_exhausted() -> None:
    # With velocity already down to one entry, an over-budget bundle must fall
    # through to trimming open_items (tail-first) and then manifest (tail-first)
    # down to one entry each, never past it.
    ctx = PlanContext(
        manifest=[
            {"tool": "MyTester", "repo": "my-tester", "title": "t", "added": "", "depends_on": []},
            {
                "tool": "MyReviewer",
                "repo": "my-reviewer",
                "title": "t2",
                "added": "",
                "depends_on": [],
            },
        ],
        open_items=["gap one", "gap two"],
        velocity=[{"repo": "r", "kind": "build", "detail": "only entry", "ts": "2026-07-01"}],
    )

    trimmed = truncate(ctx, budget=1)  # forces every stage to trim down to its floor

    assert trimmed.velocity == ctx.velocity  # already at the floor, untouched
    assert trimmed.open_items == ["gap one"]  # tail dropped
    assert trimmed.manifest == [ctx.manifest[0]]  # tail dropped


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


def test_parse_plan_rejects_a_non_dict_item() -> None:
    text = '{"plan": ["not-a-dict"], "flags": []}'
    assert _parse_plan(text) is None


def test_parse_plan_rejects_item_with_missing_or_bad_horizon() -> None:
    text = (
        '{"plan": [{"item": "my-tester", "rationale": "go", "horizon": "eventually"}],'
        ' "flags": []}'
    )
    assert _parse_plan(text) is None


def test_upsert_preserves_following_section() -> None:
    body = "## Recommended sequence\n\n1. old\n\n## Other section\n\nkeep me\n"
    plan = Plan(items=[{"item": "my-tester", "rationale": "go", "horizon": "next"}])

    out = upsert_section(body, render_section(plan))

    assert "## Other section" in out
    assert "keep me" in out
    assert "old" not in out


def test_upsert_append_path_handles_backslashes_in_plan_text() -> None:
    # The append path (no existing section) builds the body via plain string
    # concatenation, not re.sub, so it never had the escape-parsing bug — this
    # just confirms both code paths handle backslashes.
    plan = Plan(
        items=[
            {
                "item": "my-tester",
                "rationale": r"see \1 backreference-looking text",
                "horizon": "next",
            }
        ]
    )
    body = "# Fleet tracking\n\n- [ ] a task\n"

    out = upsert_section(body, render_section(plan))

    assert r"\1 backreference-looking text" in out


def test_upsert_replace_handles_backslashes_in_replacement_text_literally() -> None:
    # Regression for issue #9: a naive `_SECTION_RE.sub(block, body)` treats
    # `block` as a replacement pattern, so backslash sequences from
    # Engine-produced item text (e.g. "\1", "\g<name>") are parsed as group
    # references and either crash or silently corrupt the issue body.
    body = "## Recommended sequence\n\nold\n"
    plan = Plan(
        items=[
            {
                "item": r"fix path C:\1\2 handling",
                "rationale": r"regex \g<name> escape check",
                "horizon": "next",
            }
        ]
    )

    out = upsert_section(body, render_section(plan))

    assert r"fix path C:\1\2 handling" in out
    assert r"\g<name>" in out
    assert out.count("## Recommended sequence") == 1
