"""Combines T4.2's code scorers and T4.3's safety invariants into one
pass/fail result. Per CP4's demo (a regression blocks CI): any invariant
violation fails the whole suite, regardless of how good the accuracy scores
are. Accuracy can regress a little and still ship with a warning; a safety
invariant cannot regress at all.
"""
from __future__ import annotations

from dataclasses import dataclass

from evals.golden import GoldenCase
from evals.invariants import InvariantViolation, check_all
from evals.scorers import CaseScore, score_all


@dataclass
class SuiteResult:
    scores: list[CaseScore]
    violations: list[InvariantViolation]

    @property
    def passed(self) -> bool:
        return not self.violations


def run_suite(cases: list[GoldenCase]) -> SuiteResult:
    return SuiteResult(scores=score_all(cases), violations=check_all(cases))
