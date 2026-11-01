"""Tests for app/complaints.py and the committed fixtures/complaints/complaints.json.
No test here calls an LLM: load_complaints() only reads the committed JSON file."""
import ast
import inspect

from app.complaints import COMPLAINTS_FIXTURE, load_complaints
from app.generate_data import generate_dataset

INJECTION_MARKERS = ("ignore your previous instructions", "system note", "admin mode",
                     "disregard", "override")


def test_complaints_load_from_the_committed_fixture():
    complaints = load_complaints()
    assert COMPLAINTS_FIXTURE.exists()
    assert len(complaints) == 200


def test_seeder_attaches_complaint_text_to_every_dispute():
    dataset = generate_dataset(42)
    assert len(dataset.disputes) == 200
    for disp in dataset.disputes:
        assert disp.complaint_text
        assert isinstance(disp.complaint_text, str)


def test_complaint_ids_match_dispute_ids_for_any_seed():
    complaints = load_complaints()
    for seed in (1, 2, 42):
        dataset = generate_dataset(seed)
        disp_ids = {d.disp_id for d in dataset.disputes}
        assert disp_ids == set(complaints.keys())


def test_adversarial_disputes_include_prompt_injection_attempts():
    dataset = generate_dataset(42)
    answer_by_disp_id = {row.disp_id: row for row in dataset.answer_key}
    adversarial = [d for d in dataset.disputes if answer_by_disp_id[d.disp_id].category == "adversarial"]
    assert len(adversarial) == 20
    for disp in adversarial:
        text_lower = disp.complaint_text.lower()
        assert any(marker in text_lower for marker in INJECTION_MARKERS), disp.complaint_text


def test_non_adversarial_disputes_have_no_injection_markers():
    dataset = generate_dataset(42)
    answer_by_disp_id = {row.disp_id: row for row in dataset.answer_key}
    non_adversarial = [d for d in dataset.disputes if answer_by_disp_id[d.disp_id].category != "adversarial"]
    for disp in non_adversarial:
        text_lower = disp.complaint_text.lower()
        assert not any(marker in text_lower for marker in INJECTION_MARKERS), disp.complaint_text


def test_no_network_or_llm_api_calls_in_complaint_generation_code():
    """Source-scans app/complaints.py and app/generate_data.py's import statements for
    any network/LLM client usage, proving dataset generation can never call an LLM."""
    import app.complaints
    import app.generate_data

    forbidden_modules = {"requests", "httpx", "urllib", "anthropic", "openai", "socket"}
    for module in (app.complaints, app.generate_data):
        tree = ast.parse(inspect.getsource(module))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(n.name.split(".")[0] for n in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert not (imported & forbidden_modules), f"{module.__name__} imports {imported & forbidden_modules}"
