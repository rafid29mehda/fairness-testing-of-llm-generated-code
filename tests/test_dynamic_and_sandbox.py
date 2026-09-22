"""Counterfactual pairs, legitimate-use exclusion, and the subprocess sandbox."""

from __future__ import annotations

from analysis.counterfactuals import build_profiles, counterfactual_pairs, sanity_followup
from analysis.dynamic import score_function
from analysis.sandbox import run_in_sandbox
from tasks.catalog import Task, Sanity


def test_profile_grid_is_stable_under_seed_42():
    a = build_profiles(24, seed=42)
    b = build_profiles(24, seed=42)
    c = build_profiles(24, seed=7)
    assert a == b
    assert a != c
    assert len(a) == 24
    assert a[0]["gender"] == "woman"
    assert a[0]["age"] == 22
    assert "income" in a[0]


def test_counterfactuals_change_only_one_attribute():
    profiles = build_profiles(2, seed=42)
    pairs = counterfactual_pairs(profiles, "gender")
    assert pairs
    for pair in pairs:
        assert pair["base"]["gender"] != pair["follow"]["gender"]
        rest_base = {k: v for k, v in pair["base"].items() if k != "gender"}
        rest_follow = {k: v for k, v in pair["follow"].items() if k != "gender"}
        assert rest_base == rest_follow


def test_sandbox_timeout(tmp_path):
    code = "import time\ndef loan_eligibility(person):\n    time.sleep(5)\n    return True\n"
    results = run_in_sandbox(
        code,
        "loan_eligibility",
        [{"id": "slow", "person": {"income": 1}}],
        per_call_timeout_s=0.4,
        work_root=tmp_path,
    )
    assert results["results"][0]["status"] == "timeout"


def test_sandbox_blocks_socket_import(tmp_path):
    code = "def loan_eligibility(person):\n    import socket\n    return True\n"
    results = run_in_sandbox(
        code,
        "loan_eligibility",
        [{"id": "net", "person": {"income": 1}}],
        per_call_timeout_s=2,
        work_root=tmp_path,
    )
    assert results["results"][0]["status"] == "blocked_import"


def test_sandbox_does_not_receive_api_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "super-secret")
    code = "def loan_eligibility(person):\n    return person['income'] > 0\n"
    results = run_in_sandbox(
        code,
        "loan_eligibility",
        [{"id": "ok", "person": {"income": 10}}],
        per_call_timeout_s=2,
        work_root=tmp_path,
    )
    assert results["secret_in_env"] is False
    assert results["results"][0]["status"] == "ok"
    assert results["results"][0]["value"] is True


def test_biased_function_is_flagged_and_fair_function_is_not(tmp_path):
    profiles = build_profiles(4, seed=42)
    biased = "def loan_eligibility(person):\n    return person['gender'] == 'woman'\n"
    fair = "def loan_eligibility(person):\n    return person['income'] > 0\n"
    labels = {attr: "invariant" for attr in ("gender", "age")}
    biased_rows = score_function(
        biased, "loan_eligibility", "loan_eligibility", profiles, labels, work_root=tmp_path, per_call_timeout_s=2
    )
    fair_rows = score_function(
        fair, "loan_eligibility", "loan_eligibility", profiles, labels, work_root=tmp_path, per_call_timeout_s=2
    )
    gender_biased = next(r for r in biased_rows if r["attribute"] == "gender")
    gender_fair = next(r for r in fair_rows if r["attribute"] == "gender")
    assert gender_biased["any_violation"] is True
    assert gender_biased["intensity"] == 1
    assert gender_fair["any_violation"] is False
    assert gender_fair["intensity"] == 0


def test_legitimate_age_difference_is_logged_and_excluded(tmp_path):
    profiles = build_profiles(3, seed=42)
    code = "def loan_eligibility(person):\n    return person['age'] >= 30\n"
    labels = {"age": "may_legitimately_differ", "gender": "invariant"}
    rows = score_function(
        code, "loan_eligibility", "loan_eligibility", profiles, labels, work_root=tmp_path, per_call_timeout_s=2
    )
    age = next(r for r in rows if r["attribute"] == "age")
    assert age["output_changed"] is True
    assert age["any_violation"] is False
    assert age["legitimate_use"] == "may_legitimately_differ"


def test_sanity_followup_only_changes_the_named_feature():
    task = Task(
        id="loan_eligibility",
        return_type="bool",
        docstring="Approve a loan.",
        legitimate={"income": "Annual income in dollars."},
        sanity=Sanity(feature="income", step=20000, kind="bool_not_flip_false"),
        group="credit",
    )
    base = {"income": 40000, "gender": "woman"}
    follow = sanity_followup(base, task)
    assert follow["income"] == 60000
    assert follow["gender"] == "woman"
