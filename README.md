# my-planner

[![CI](https://github.com/MyThingsLab/my-planner/actions/workflows/ci.yml/badge.svg)](https://github.com/MyThingsLab/my-planner/actions/workflows/ci.yml) [![codecov](https://codecov.io/gh/MyThingsLab/my-planner/branch/main/graph/badge.svg)](https://codecov.io/gh/MyThingsLab/my-planner) ![Python](https://img.shields.io/badge/python-3.11%2B-blue) [![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A [MyThingsLab](../mythings-core) `My[X]` tool. It produces a **priority-ordered,
multi-item plan** across the whole fleet backlog — the recommended order for the
next several units of work, and why — on a rolling basis.

It is deliberately **not** a duplicate of two tools that already exist:

- **MyOrchestrator** picks *the single next unit of work, right now*. MyPlanner
  produces a *sequence with rationale*, and feeds its `flags`/horizons back into
  MyOrchestrator's ranking as one more signal.
- **MyAdvisor** answers *one posed question*, reactively. MyPlanner runs
  proactively over the whole backlog.

## What it does each run

1. Reads the unbuilt-tools dependency graph from MyOrchestrator's `manifest.json`.
2. Reads open decisions + safety gaps — from MyProjector's synced board if it
   exists, else the raw org-wide tracking issue.
3. Reads the last N `decision`/`ship`/`build` ledger entries fleet-wide (a
   velocity signal).
4. Caps the combined bundle to a fixed size, trimming lowest-relevance first.
5. Calls the Engine **once** (always, even on an empty backlog) to produce the
   plan and any pacing `flags`.

Output shape:

```json
{"plan": [{"item": "...", "rationale": "...", "horizon": "next|soon|later"}],
 "flags": ["pause new tools, close a safety gap first"]}
```

The plan is written to the ledger (`kind=plan`) and appended/updated as a
`## Recommended sequence` section on the org-wide tracking issue
(`Action(kind="tracking-issue-edit")`, `ASK` by default).

## CLI

```bash
myplanner plan --engine claude-cli [--horizon 4w] [--json] \
  [--tracking-repo MyThingsLab/mythings-core --tracking-issue 1]
```

## Install (development)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ../mythings-core -e ".[dev]"
pytest
```

## License

MIT — see [`LICENSE`](LICENSE).
