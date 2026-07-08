# my-planner — agent instructions

You are developing **my-planner**, a MyThingsLab My[X] tool.

**Inherited rules:** obey [`./HARNESS.md`](./HARNESS.md) in full — the vendored
MyThingsLab build-harness rules. Do not restate or override them. Anything not
covered here defers to `HARNESS.md`, then `my-things-core/docs/CONVENTIONS.md`.

## This tool

- **Purpose:** produce and maintain a priority-ordered, multi-item plan — "here's
  the recommended order for the next several units of work, and why" — grounded
  in the whole backlog (unbuilt-tools dependency graph, open decisions, safety
  gaps, recent ledger velocity). It plans a *sequence*; it never picks or
  dispatches a single unit (that's MyOrchestrator) and never answers a single
  posed question (that's MyAdvisor).
- **The single Engine call:** required — a plan can't come from a fixed reply.
  Input is a deterministically assembled, size-capped context bundle; output is
  `{"plan": [{"item", "rationale", "horizon"}], "flags": [...]}`. Against
  `NoopEngine` it degrades to an explicit placeholder plan (plumbing only, not a
  real recommendation).
- **Invariants / rules:**
  - Never picks or dispatches work; never invokes another tool's CLI. It emits a
    recommendation and feeds `flags`/horizons into MyOrchestrator's ranking as
    one more signal, the same role its drift/ask urgency boosts already play.
  - One side effect: append/update a `## Recommended sequence` section on the
    org-wide tracking issue — `Action(kind="tracking-issue-edit")`, **`ASK`** by
    default (reuses MyProjector's classification for editing public content).
  - Always calls the Engine, even on an empty backlog — "things look calm" is
    still a judgment worth recording.
- **Backlog label:** `my-planner`.
