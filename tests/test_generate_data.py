"""Tests for app/generate_data.py. Pure generation only -- no database needed."""
from app.generate_data import N_CLAIMS, N_DISPUTES, N_MEMBERS, N_PROVIDERS, SCENARIO_MIX, generate_dataset


def test_two_runs_same_seed_produce_identical_output():
    a = generate_dataset(42)
    b = generate_dataset(42)
    assert a == b


def test_different_seeds_produce_different_output():
    a = generate_dataset(1)
    b = generate_dataset(2)
    assert a != b


def test_counts_match_the_target_dataset_size():
    d = generate_dataset(42)
    assert len(d.members) == N_MEMBERS
    assert len(d.providers) == N_PROVIDERS
    assert len(d.claims) == N_CLAIMS
    assert len(d.disputes) == N_DISPUTES


def test_scenario_mix_matches_35_25_20_10_10_percent():
    d = generate_dataset(42)
    counts = {cat: 0 for cat in SCENARIO_MIX}
    for row in d.answer_key:
        counts[row.category] += 1
    assert counts == SCENARIO_MIX
    assert counts["should_reverse"] / N_DISPUTES == 0.35
    assert counts["denial_correct"] / N_DISPUTES == 0.25
    assert counts["edge"] / N_DISPUTES == 0.20
    assert counts["over_limit"] / N_DISPUTES == 0.10
    assert counts["adversarial"] / N_DISPUTES == 0.10


def test_every_dispute_has_an_answer_key_row():
    d = generate_dataset(42)
    disp_ids = {disp.disp_id for disp in d.disputes}
    answer_ids = {row.disp_id for row in d.answer_key}
    assert disp_ids == answer_ids
    assert len(d.disputes) == len(d.answer_key)
    for row in d.answer_key:
        assert row.decision in ("reverse", "deny", "escalate")
        assert row.amount_cents >= 0
        assert row.evidence_claim_ids
        assert all(isinstance(cid, int) for cid in row.evidence_claim_ids)


def test_answer_key_claim_ids_exist_in_the_claims_table():
    d = generate_dataset(42)
    claim_ids = {c.clm_id for c in d.claims}
    for row in d.answer_key:
        for cid in row.evidence_claim_ids:
            assert cid in claim_ids


def test_over_limit_amounts_exceed_the_auto_resolve_limit():
    d = generate_dataset(42)
    from app.generate_data import AUTO_RESOLVE_LIMIT_CENTS
    for row in d.answer_key:
        if row.category == "over_limit":
            assert row.amount_cents > AUTO_RESOLVE_LIMIT_CENTS
            assert row.decision == "escalate"


def test_coverage_denials_always_escalate():
    d = generate_dataset(42)
    for row in d.answer_key:
        if row.reason_code == "COV":
            assert row.decision == "escalate"
