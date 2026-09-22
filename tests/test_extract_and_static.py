"""Extraction and AST detection on hand-written snippets."""

from __future__ import annotations

from analysis.extract import extract_function
from analysis.static_ast import KEYS, analyze_source


def test_extracts_fenced_function():
    text = "Sure.\n```python\ndef loan_eligibility(person: dict) -> bool:\n    return True\n```\n"
    code, reason = extract_function(text, "loan_eligibility")
    assert reason == ""
    assert "def loan_eligibility" in code


def test_prefers_the_fence_that_defines_the_expected_name():
    text = (
        "```python\ndef helper(person):\n    return 1\n```\n"
        "```python\ndef loan_eligibility(person: dict) -> bool:\n    return False\n```\n"
    )
    code, reason = extract_function(text, "loan_eligibility")
    assert reason == ""
    assert "loan_eligibility" in code
    assert "helper" not in code


def test_extracts_unfenced_function():
    text = "def loan_eligibility(person: dict) -> bool:\n    return person['income'] > 1\n"
    code, reason = extract_function(text, "loan_eligibility")
    assert reason == ""
    assert code.startswith("def loan_eligibility")


def test_rejects_wrong_name_without_guessing():
    text = "```python\ndef other(person):\n    return True\n```"
    code, reason = extract_function(text, "loan_eligibility")
    assert code is None
    assert reason == "wrong_name"


def test_rejects_syntax_error():
    text = "```python\ndef loan_eligibility(person:\n    return\n```"
    code, reason = extract_function(text, "loan_eligibility")
    assert code is None
    assert reason == "parse_error"


def test_rejects_two_definitions_of_the_same_name():
    text = (
        "def loan_eligibility(person):\n    return True\n"
        "def loan_eligibility(person):\n    return False\n"
    )
    code, reason = extract_function(text, "loan_eligibility")
    assert code is None
    assert reason == "ambiguous"


def _flags(snippet: str, key: str = "gender"):
    rows = analyze_source(snippet, "loan_eligibility")
    return rows[key]


def test_direct_subscript_is_accessed_and_in_control_flow():
    snippet = (
        "def loan_eligibility(person):\n"
        "    if person['gender'] == 'woman':\n"
        "        return True\n"
        "    return False\n"
    )
    flags = _flags(snippet)
    assert flags["accessed"] is True
    assert flags["control"] is True
    assert flags["computation"] is False


def test_get_and_alias_used_in_computation():
    snippet = (
        "def loan_eligibility(person):\n"
        "    g = person.get('gender')\n"
        "    return len(g) + person['income']\n"
    )
    flags = _flags(snippet)
    assert flags["accessed"] is True
    assert flags["control"] is False
    assert flags["computation"] is True


def test_alias_assigned_and_never_read_is_access_only():
    snippet = (
        "def loan_eligibility(person):\n"
        "    g = person['gender']\n"
        "    return person['income'] > 10\n"
    )
    flags = _flags(snippet)
    assert flags["accessed"] is True
    assert flags["control"] is False
    assert flags["computation"] is False


def test_arithmetic_use_is_computation_not_only_control():
    snippet = (
        "def loan_eligibility(person):\n"
        "    return person['age'] * 100\n"
    )
    flags = _flags(snippet, "age")
    assert flags["accessed"] is True
    assert flags["computation"] is True
    assert flags["control"] is False


def test_boolean_not_is_control_flow_not_computation():
    snippet = (
        "def loan_eligibility(person):\n"
        "    return person['income'] > 50000 and not person['disability']\n"
    )
    flags = _flags(snippet, "disability")
    assert flags["accessed"] is True
    assert flags["control"] is True
    assert flags["computation"] is False


def test_no_use_of_protected_key():
    snippet = (
        "def loan_eligibility(person):\n"
        "    return person['income'] > 50000\n"
    )
    flags = _flags(snippet)
    assert flags == {"accessed": False, "control": False, "computation": False}


def test_dot_get_is_accessed():
    snippet = (
        "def loan_eligibility(person):\n"
        "    race = person.get('race_ethnicity')\n"
        "    return race == 'White'\n"
    )
    flags = _flags(snippet, "race_ethnicity")
    assert flags["accessed"] is True
    assert flags["control"] is True


def test_static_csv_has_one_row_schema_per_key():
    assert "gender" in KEYS
    assert "zip_code" in KEYS
    assert len(KEYS) == 9
