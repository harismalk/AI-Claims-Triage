"""Marks a tool function as having a side effect (it writes).

T2.3's tool runtime checks this to fail closed on undeclared writes outside
live mode. Per [[DEC-0001-propose-gate-execute]], only executors behind the
decision gate call these; a specialist never calls a side_effect tool itself.
"""
from __future__ import annotations

from typing import Callable, TypeVar

F = TypeVar("F", bound=Callable)


def side_effect(fn: F) -> F:
    fn.side_effect = True
    return fn


def is_side_effect(fn: Callable) -> bool:
    return bool(getattr(fn, "side_effect", False))
