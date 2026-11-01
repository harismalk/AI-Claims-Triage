"""Letter-quality judge: scores a resolution letter (T3.5) 1-5 against the
written rubric (evals/letter_rubric.md).

Per [[DEC-0005-specialist-reason-fn]]'s pattern, the judgment step is a
pluggable judge_fn, defaulting to a deterministic rubric-dimension checker,
so tests run offline. This is the one eval component
record/1-truth/ARCH-system-overview.md marks "LLM: judge only" -- wiring in
a real model's judgment eventually matters more here than anywhere else in
the project; judge_fn is the seam for that.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

RUBRIC = (Path(__file__).resolve().parent / "letter_rubric.md").read_text()

JARGON_PATTERNS = (
    re.compile(r"\b(DUP|BIL|DOC|COV)\b"),
    re.compile(r"\b(BRONZE|SILVER|GOLD|HDHP_2000)\b"),
    re.compile(r"\b(?:\d{5}|J\d{4})\b"),             # procedure codes
    re.compile(r"\bclaim\s+\d+\b", re.IGNORECASE),
)


@dataclass
class LetterJudgment:
    score: int  # 1-5
    dimension_scores: dict[str, bool]
    notes: str


def default_judge_fn(letter: str, member_name: str, issues_payment: bool) -> LetterJudgment:
    """Deterministic proxy for the rubric's five checkable dimensions.
    score = max(1, number of dimensions satisfied)."""
    dims = {
        "greeting": letter.strip().lower().startswith(f"dear {member_name.lower()}"),
        "clear_decision": any(p in letter.lower() for p in
                               ("issuing a payment", "no additional payment",
                                "original decision was correct")),
        "amount_stated_correctly": (not issues_payment) or bool(re.search(r"\$\d+\.\d{2}", letter)),
        "plain_language_no_jargon": not any(p.search(letter) for p in JARGON_PATTERNS),
        "professional_closing": "sincerely" in letter.lower(),
    }
    failed = [name for name, ok in dims.items() if not ok]
    score = max(1, sum(dims.values()))
    notes = "all dimensions satisfied" if not failed else f"failed: {', '.join(failed)}"
    return LetterJudgment(score=score, dimension_scores=dims, notes=notes)


def judge_letter(
    letter: str,
    member_name: str,
    issues_payment: bool,
    judge_fn: Callable[[str, str, bool], LetterJudgment] = default_judge_fn,
) -> LetterJudgment:
    """Score a letter against the rubric.

    Args:
        letter: the letter text.
        member_name: the member's name, to check the greeting.
        issues_payment: True if this letter is for a "reverse" decision
            (a payment is being issued), False for "deny" (upheld).
        judge_fn: the judgment step; swappable for a real LLM.

    Returns:
        A LetterJudgment.
    """
    return judge_fn(letter, member_name, issues_payment)
