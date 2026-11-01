"""Tests for evals/judge.py and evals/judge_calibration.py.

Most of this needs no database at all -- the judge only ever looks at letter
text. One integration test confirms a real T3.5-generated letter (which does
need the live DB) scores a clean 5.
"""
import psycopg2
import pytest

from app.gate import evaluate
from app.generate_data import default_dsn, generate_dataset, load_into_postgres
from app.letters import draft_letter
from app.specialists.duplicate_denial.specialist import propose
from app.tool_runtime import ToolRuntime
from evals.judge import RUBRIC, default_judge_fn, judge_letter
from evals.judge_calibration import calibrate, load_hand_graded

GOOD_LETTER = (
    "Dear Avery Thistlewood,\n\n"
    "We have reviewed your dispute and found that the charge was mistakenly treated as a duplicate "
    "when it was a separate service. We are issuing a payment of $42.50 to resolve this matter.\n\n"
    "If you have any questions about this decision, please contact Member Services.\n\n"
    "Sincerely,\nMember Services"
)


def test_rubric_is_a_written_document():
    assert "Greeting" in RUBRIC
    assert "jargon" in RUBRIC.lower()


def test_clean_letter_scores_5():
    judgment = judge_letter(GOOD_LETTER, "Avery Thistlewood", issues_payment=True)
    assert judgment.score == 5
    assert all(judgment.dimension_scores.values())


def test_missing_greeting_is_detected():
    letter = GOOD_LETTER.split("\n\n", 1)[1]  # drop the greeting line
    judgment = judge_letter(letter, "Avery Thistlewood", issues_payment=True)
    assert judgment.dimension_scores["greeting"] is False
    assert judgment.score < 5


def test_missing_amount_on_a_payment_letter_is_detected():
    letter = GOOD_LETTER.replace("$42.50", "an amount")
    judgment = judge_letter(letter, "Avery Thistlewood", issues_payment=True)
    assert judgment.dimension_scores["amount_stated_correctly"] is False


def test_no_amount_required_when_not_issuing_payment():
    letter = "Dear Avery Thistlewood,\n\nAfter review, the original decision was correct, and no additional payment is owed.\n\nSincerely,\nMember Services"
    judgment = judge_letter(letter, "Avery Thistlewood", issues_payment=False)
    assert judgment.dimension_scores["amount_stated_correctly"] is True


def test_jargon_leak_is_detected():
    for jargon in ("claim 123", "DUP", "GOLD plan", "99213"):
        letter = GOOD_LETTER.replace("your dispute", f"your dispute ({jargon})")
        judgment = judge_letter(letter, "Avery Thistlewood", issues_payment=True)
        assert judgment.dimension_scores["plain_language_no_jargon"] is False, jargon


def test_missing_closing_is_detected():
    letter = GOOD_LETTER.rsplit("\n\n", 1)[0]
    judgment = judge_letter(letter, "Avery Thistlewood", issues_payment=True)
    assert judgment.dimension_scores["professional_closing"] is False


def test_score_never_drops_below_1():
    judgment = judge_letter("nonsense", "Nobody", issues_payment=True)
    assert judgment.score >= 1


def test_custom_judge_fn_is_pluggable():
    def always_perfect(letter, member_name, issues_payment):
        from evals.judge import LetterJudgment
        return LetterJudgment(score=5, dimension_scores={}, notes="stub")

    result = judge_letter("anything", "Anyone", True, judge_fn=always_perfect)
    assert result.score == 5


# ------------------------------------------------------------- calibration

def test_hand_graded_fixture_has_about_30_examples():
    examples = load_hand_graded()
    assert 25 <= len(examples) <= 35
    for ex in examples:
        assert 1 <= ex["hand_score"] <= 5


def test_judge_calibration_is_measured_and_reported():
    result = calibrate()
    assert result["n"] >= 25
    # A cheap deterministic proxy judge is expected to disagree with real
    # qualitative grading sometimes (tone, nonsensical content, severity of
    # jargon leaks aren't fully captured by pattern matching) -- these
    # thresholds document that it's a reasonable, not perfect, proxy.
    assert result["exact_match_rate"] >= 0.3
    assert result["within_one_point_rate"] >= 0.6
    assert result["mean_absolute_error"] <= 1.5


# ------------------------------------------------------------- integration

@pytest.fixture(scope="module", autouse=True)
def seeded_db():
    try:
        conn = psycopg2.connect(default_dsn())
        conn.close()
    except psycopg2.OperationalError:
        pytest.skip("Postgres is not reachable; start it with `docker compose up -d`", allow_module_level=True)
    load_into_postgres(generate_dataset(42), default_dsn())


def test_real_generated_letter_scores_well():
    dataset = generate_dataset(42)
    row = next(r for r in dataset.answer_key if r.reason_code == "DUP" and r.category == "should_reverse")
    runtime = ToolRuntime(mode="live")
    proposal = propose(row.disp_id, runtime)
    decision = evaluate(proposal, runtime)
    assert decision.action == "auto_resolve"

    letter = draft_letter(decision, runtime)
    member = runtime.call("get_member", member_id=runtime.call("get_dispute", dispute_id=row.disp_id).claim.member_id)
    member_name = f"{member.first_name} {member.last_name}"

    judgment = judge_letter(letter, member_name, issues_payment=True)
    assert judgment.score == 5, judgment.notes
