"""Every task renders every template, and the function name is in the prompt."""

from __future__ import annotations

from pathlib import Path

from prompts.templates import VARIANTS, render
from tasks.catalog import load_labels, load_tasks


ROOT = Path(__file__).resolve().parents[1]


def test_sixteen_tasks_and_full_label_table():
    tasks = load_tasks(ROOT / "tasks" / "tasks.yaml")
    labels = load_labels(ROOT / "tasks" / "legitimate_use.csv")
    assert len(tasks) == 16
    protected = ["gender", "race_ethnicity", "age", "religion", "disability", "marital_status"]
    assert len(labels) == 16 * len(protected)
    credit = {"loan_eligibility", "credit_limit", "mortgage_rate", "customer_credit_increase"}
    for task in tasks:
        for attr in protected:
            label = labels[(task.id, attr)]
            if task.id in credit and attr == "age":
                assert label.label == "may_legitimately_differ"
                assert "1002" in label.source
            else:
                assert label.label == "invariant"
            assert label.source


def test_every_template_names_the_function():
    tasks = load_tasks(ROOT / "tasks" / "tasks.yaml")
    for task in tasks:
        for variant in VARIANTS:
            if variant == "feedback_repair":
                text = render(task, variant, previous_code="def " + task.id + "(person):\n    return True\n", report="no violation")
            elif variant == "self_review":
                text = render(task, variant, previous_code="def " + task.id + "(person):\n    return True\n")
            else:
                text = render(task, variant)
            assert "def " + task.id + "(person: dict)" in text or task.id in text
            assert task.id in text


def test_proxy_prompt_omits_protected_keys_and_includes_proxies():
    tasks = load_tasks(ROOT / "tasks" / "tasks.yaml")
    text = render(tasks[0], "detailed_proxy")
    assert "zip_code" in text
    assert "first_name" in text
    assert "native_language" in text
    assert '"gender"' not in text
    assert '"race_ethnicity"' not in text


def test_mitigation_names_protected_attributes():
    tasks = load_tasks(ROOT / "tasks" / "tasks.yaml")
    text = render(tasks[0], "mitigation_direct")
    for key in ("gender", "race_ethnicity", "age", "religion", "disability", "marital_status"):
        assert key in text
    assert "do not use" in text.lower() or "Do not use" in text
