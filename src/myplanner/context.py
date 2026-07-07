from __future__ import annotations

import json
from dataclasses import dataclass, field

# The same "shortlist from a corpus, then cite" shape MyAdvisor/MyWiki/MySearcher
# use: assemble a deterministic bundle, cap it to a fixed size trimming
# lowest-relevance first, then hand it to a single Engine call. (README's
# cross-cutting note flags promoting this helper into core once the reuse
# question is settled; kept local for v0.)

DEFAULT_BUDGET = 12_000  # chars of serialized bundle handed to the Engine


@dataclass
class PlanContext:
    manifest: list[dict] = field(default_factory=list)  # unbuilt tools (dep graph)
    open_items: list[str] = field(default_factory=list)  # open decisions + safety gaps
    velocity: list[dict] = field(default_factory=list)  # recent ledger entries

    def to_bundle(self) -> dict:
        return {
            "unbuilt_tools": self.manifest,
            "open_decisions_and_gaps": self.open_items,
            "recent_activity": self.velocity,
        }

    @property
    def is_empty(self) -> bool:
        return not (self.manifest or self.open_items or self.velocity)


def _size(ctx: PlanContext) -> int:
    return len(json.dumps(ctx.to_bundle(), separators=(",", ":")))


def truncate(ctx: PlanContext, *, budget: int = DEFAULT_BUDGET) -> PlanContext:
    # Trim lowest-relevance first: oldest velocity entries, then the tail of the
    # open-items list, then the tail of the manifest. Never trims to empty while
    # anything is over budget — an empty-but-present bundle is still valid input.
    ctx = PlanContext(
        manifest=list(ctx.manifest),
        open_items=list(ctx.open_items),
        velocity=list(ctx.velocity),
    )
    for trim in (_trim_velocity, _trim_open_items, _trim_manifest):
        while _size(ctx) > budget and trim(ctx):
            pass
        if _size(ctx) <= budget:
            break
    return ctx


def _trim_velocity(ctx: PlanContext) -> bool:
    if len(ctx.velocity) <= 1:
        return False
    ctx.velocity.pop(0)  # oldest first
    return True


def _trim_open_items(ctx: PlanContext) -> bool:
    if len(ctx.open_items) <= 1:
        return False
    ctx.open_items.pop()
    return True


def _trim_manifest(ctx: PlanContext) -> bool:
    if len(ctx.manifest) <= 1:
        return False
    ctx.manifest.pop()
    return True
