"""One runtime under every tool call, per record/1-truth/ARCH-system-overview.md.

Modes:
    live   -- calls the real tool function, which talks to the live Postgres
              legacy database. Every call is recorded to `history`.
    replay -- never touches the live legacy database.
              * A read first looks for a matching call in the recorded
                `replay_source` trace fed into the runtime; if not found,
                falls through to an in-memory `snapshot` dict; a miss when
                neither has an answer raises StrictMissError (unless
                strict=False).
              * A write is never applied to Postgres. It is appended to
                `effect_log` and its effect is merged into an in-memory
                copy-on-write `overlay`, which every subsequent read in this
                runtime instance is patched through -- so a write made during
                replay is immediately visible to later reads in the same
                session, without the real database ever being touched.

Calling a tool with no @tool declaration (app.tool_meta) is blocked outside
live mode (fail closed): the runtime cannot know whether it is safe to serve
from a recording or must be treated as a write.

The calling code (e.g. a specialist's tool-use loop) is identical in both
modes -- it only ever calls `runtime.call(tool_name, **kwargs)`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from app import tool_meta, tools, write_tools

TOOL_REGISTRY: dict[str, Callable] = {
    "lookup_claim": tools.lookup_claim,
    "find_similar_claims": tools.find_similar_claims,
    "get_plan_terms": tools.get_plan_terms,
    "get_payment_history": tools.get_payment_history,
    "get_dispute": tools.get_dispute,
    "update_claim_status": write_tools.update_claim_status,
    "issue_adjustment": write_tools.issue_adjustment,
}

# Tools with no dependency on the legacy database at all (e.g. plan terms come
# from a fixture file) are always safe to call directly, in any mode.
DB_INDEPENDENT_TOOLS = {"get_plan_terms"}

# How each write tool's effect patches the in-memory overlay, keyed by
# (table, row_id) -> field patch, using the clean field names of app.tools's
# return models (not legacy column names).
EffectApplier = Callable[[dict], dict[tuple[str, int], dict]]
EFFECT_APPLIERS: dict[str, EffectApplier] = {
    "update_claim_status": lambda kwargs: {
        ("clm_hdr", kwargs["claim_id"]): {"status_code": kwargs["new_status_code"]}
    },
    "issue_adjustment": lambda kwargs: {
        ("clm_hdr", kwargs["claim_id"]): {"paid_amount_cents": kwargs["amount_cents"]}
    },
}


class ToolRuntimeError(Exception):
    """Base class for tool runtime errors."""


class UndeclaredToolError(ToolRuntimeError):
    """A tool with no @tool(side_effect=...) declaration was called outside live mode."""


class StrictMissError(ToolRuntimeError):
    """A replay-mode read matched neither the replay trace nor the snapshot."""


@dataclass
class ToolCallRecord:
    tool_name: str
    kwargs: dict
    result: Any


def build_snapshot(claim_ids: list[int] = (), dispute_ids: list[int] = ()) -> dict[tuple[str, int], Any]:
    """Build an in-memory snapshot dict for replay-mode fallback reads, by
    calling the real (live) tools once. Call this while live, before switching
    to replay, so replay never needs the live database again."""
    snapshot: dict[tuple[str, int], Any] = {}
    for claim_id in claim_ids:
        result = tools.lookup_claim(claim_id)
        if result is not None:
            snapshot[("clm_hdr", claim_id)] = result
    for dispute_id in dispute_ids:
        result = tools.get_dispute(dispute_id)
        if result is not None:
            snapshot[("disp_hdr", dispute_id)] = result
    return snapshot


def _synthesize_write_result(tool_name: str, kwargs: dict):
    return write_tools.WriteResult(
        claim_id=kwargs["claim_id"],
        request_key=kwargs.get("request_key", ""),
        ok=True,
        replayed=False,
    )


class ToolRuntime:
    def __init__(
        self,
        mode: Literal["live", "replay"],
        replay_source: list[ToolCallRecord] = (),
        snapshot: dict[tuple[str, int], Any] | None = None,
        strict: bool = True,
        registry: dict[str, Callable] | None = None,
    ):
        self.mode = mode
        self.replay_source = list(replay_source)
        self.snapshot = snapshot or {}
        self.strict = strict
        self.registry = registry if registry is not None else TOOL_REGISTRY
        self.history: list[ToolCallRecord] = []
        self.effect_log: list[ToolCallRecord] = []
        self.overlay: dict[tuple[str, int], dict] = {}
        self._replay_cursor: dict[tuple, int] = {}

    def call(self, tool_name: str, **kwargs):
        fn = self.registry.get(tool_name)
        if fn is None:
            raise ToolRuntimeError(f"unknown tool '{tool_name}'")
        if self.mode != "live" and not tool_meta.is_declared_tool(fn):
            raise UndeclaredToolError(
                f"tool '{tool_name}' has no side_effect declaration; blocked outside live mode"
            )

        if self.mode == "live":
            result = fn(**kwargs)
        elif self.mode == "replay":
            result = (
                self._replay_write(tool_name, kwargs)
                if tool_meta.is_side_effect(fn)
                else self._replay_read(tool_name, kwargs, fn)
            )
        else:
            raise ToolRuntimeError(f"unknown mode '{self.mode}'")

        self.history.append(ToolCallRecord(tool_name, dict(kwargs), result))
        return result

    def _find_in_replay_source(self, tool_name: str, kwargs: dict) -> ToolCallRecord | None:
        sig = (tool_name, tuple(sorted(kwargs.items())))
        idx = self._replay_cursor.get(sig, 0)
        matches = [r for r in self.replay_source if r.tool_name == tool_name and r.kwargs == kwargs]
        if idx < len(matches):
            self._replay_cursor[sig] = idx + 1
            return matches[idx]
        return None

    def _apply_overlay(self, result):
        if result is None:
            return result
        if hasattr(result, "claim_id") and ("clm_hdr", result.claim_id) in self.overlay:
            result = result.model_copy(update=self.overlay[("clm_hdr", result.claim_id)])
        if hasattr(result, "claim") and result.claim is not None:
            patch = self.overlay.get(("clm_hdr", result.claim.claim_id))
            if patch:
                result = result.model_copy(update={"claim": result.claim.model_copy(update=patch)})
        return result

    def _lookup_snapshot(self, tool_name: str, kwargs: dict):
        if tool_name == "lookup_claim":
            return self.snapshot.get(("clm_hdr", kwargs["claim_id"]))
        if tool_name == "get_dispute":
            return self.snapshot.get(("disp_hdr", kwargs["dispute_id"]))
        return None

    def _replay_read(self, tool_name: str, kwargs: dict, fn: Callable):
        if tool_name in DB_INDEPENDENT_TOOLS:
            return fn(**kwargs)
        match = self._find_in_replay_source(tool_name, kwargs)
        if match is not None:
            return self._apply_overlay(match.result)
        snap_result = self._lookup_snapshot(tool_name, kwargs)
        if snap_result is not None:
            return self._apply_overlay(snap_result)
        if self.strict:
            raise StrictMissError(f"no recorded or snapshot result for {tool_name}({kwargs})")
        return None

    def _replay_write(self, tool_name: str, kwargs: dict):
        match = self._find_in_replay_source(tool_name, kwargs)
        result = match.result if match is not None else _synthesize_write_result(tool_name, kwargs)
        patch_map = EFFECT_APPLIERS.get(tool_name, lambda _: {})(kwargs)
        self.overlay.update(patch_map)
        self.effect_log.append(ToolCallRecord(tool_name, dict(kwargs), result))
        return result
