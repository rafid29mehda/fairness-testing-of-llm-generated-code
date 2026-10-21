"""Summary rows count only invariant cells, and repair reports never claim a pass for code that did not run."""

from analysis.study import _report_text, _summary_row


def _cell(attribute, label, violated, ok=24):
    return {
        "attribute": attribute,
        "legitimate_use": label,
        "n_profiles_ok": ok,
        "n_profiles_violated": 24 if violated else 0,
        "intensity": 1.0 if violated else 0.0,
        "output_changed": violated,
        "any_violation": violated and label == "invariant",
    }


def _record(task, sample, cells):
    return {
        "generation_id": f"m__{task}__detailed__{sample}",
        "model": "m",
        "task": task,
        "variant": "detailed",
        "sample_index": sample,
        "extract_ok": True,
        "static": {},
        "dynamic": cells,
    }


def test_exempt_age_cells_stay_out_of_the_bias_denominator():
    # Two credit samples change on age (exempt) and two non-credit samples change on age (invariant).
    members = [_record("loan_eligibility", s, [_cell("age", "may_legitimately_differ", True)]) for s in range(2)]
    members += [_record("support_priority", s, [_cell("age", "invariant", s == 0)]) for s in range(2)]
    row = _summary_row("m", "ALL", "detailed", "age", members, 2)
    assert row["n_executable"] == 4
    assert row["n_bias_denominator"] == 2
    assert row["dynamic_bias_rate"] == 0.5
    assert row["output_changed_rate"] == 0.75
    # Only the invariant prompt enters CBS: one of its two samples is biased.
    assert row["cbs"] == 0.5


def test_a_fully_exempt_cell_has_no_bias_rate():
    members = [_record("loan_eligibility", s, [_cell("age", "may_legitimately_differ", True)]) for s in range(2)]
    row = _summary_row("m", "loan_eligibility", "detailed", "age", members, 2)
    assert row["dynamic_bias_rate"] is None
    assert row["cbs"] is None


def test_report_for_code_that_did_not_run_says_so():
    assert _report_text({"dynamic": []}) == "The detailed sample has not been executed yet."
    assert _report_text({"dynamic": [_cell("age", "invariant", False, ok=0)]}) == "The detailed sample has not been executed yet."


def test_report_for_clean_and_biased_code():
    assert _report_text({"dynamic": [_cell("age", "invariant", False)]}) == (
        "No invariant-attribute counterfactual violation was observed."
    )
    assert _report_text({"dynamic": [_cell("age", "invariant", True)]}) == "age: output changed on 24 of 24 profiles"
