"""Declares whether a tool function has a side effect (it writes).

Every tool -- read or write -- must be decorated with @tool(side_effect=...).
T2.3's tool runtime (app.tool_runtime) checks is_declared_tool() to fail closed
on any undeclared tool outside live mode, and is_side_effect() to decide
whether a replayed call is a read (served from trace/snapshot) or a write
(intercepted into the effect log, never touching the legacy system). Per
[[DEC-0001-propose-gate-execute]], only executors behind the decision gate call
side_effect tools; a specialist never calls one directly.
"""
from __future__ import annotations

from typing import Callable, TypeVar

F = TypeVar("F", bound=Callable)


def tool(*, side_effect: bool) -> Callable[[F], F]:
    def decorator(fn: F) -> F:
        fn.side_effect = side_effect
        fn.is_declared_tool = True
        return fn
    return decorator


def is_declared_tool(fn: Callable) -> bool:
    return bool(getattr(fn, "is_declared_tool", False))


def is_side_effect(fn: Callable) -> bool:
    return bool(getattr(fn, "side_effect", False))
