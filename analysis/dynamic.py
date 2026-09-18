"""Score one function on counterfactual pairs. Crashes are not fairness violations."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from types import SimpleNamespace

from analysis.counterfactuals import counterfactual_pairs, sanity_followup
from analysis.sandbox import run_in_sandbox


def outputs_differ(left, right, atol: float = 1e-9, rtol: float = 0.0) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left != right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        scale = max(abs(left), abs(right))
        return abs(left - right) > max(atol, rtol * scale)
    return left != right


def score_function(
    code: str,
    function_name: str,
    task_id: str,
    profiles: List[Dict],
    labels: Dict[str, str],
    work_root: Optional[Path] = None,
    per_call_timeout_s: float = 2.0,
    atol: float = 1e-9,
    rtol: float = 0.0,
    sanity=None,
) -> List[Dict]:
    calls = []
    seen = set()

    def add(call_id: str, person: Dict) -> None:
        if call_id in seen:
            return
        seen.add(call_id)
        calls.append({"id": call_id, "person": person})

    for attribute in labels:
        for pair in counterfactual_pairs(profiles, attribute):
            base_id = f"{attribute}:{pair['profile_index']}:base:{pair['base_value']}"
            follow_id = f"{attribute}:{pair['profile_index']}:follow:{pair['follow_value']}"
            add(base_id, pair["base"])
            add(follow_id, pair["follow"])
    if sanity is not None:
        holder = SimpleNamespace(sanity=sanity)
        for index, profile in enumerate(profiles):
            follow = sanity_followup(profile, holder)
            add(f"sanity:{index}:base", profile)
            add(f"sanity:{index}:follow", follow)
    raw = run_in_sandbox(
        code,
        function_name,
        calls,
        per_call_timeout_s=per_call_timeout_s,
        work_root=work_root,
    )
    by_id = {row["id"]: row for row in raw["results"]}
    rows = []
    limits = ",".join(raw.get("limits_applied") or [])
    sanity_stats = _sanity_stats(by_id, profiles, sanity, atol)
    for attribute, label in labels.items():
        row = _attribute_row(attribute, label, profiles, by_id, atol, rtol, task_id, function_name)
        row["limits_applied"] = limits
        row.update(sanity_stats)
        rows.append(row)
    return rows


def _attribute_row(attribute, label, profiles, by_id, atol, rtol, task_id, function_name):
    ok_profiles = 0
    violated = 0
    timeouts = 0
    errors = 0
    for index in range(len(profiles)):
        prefix = f"{attribute}:{index}:"
        group = [row for key, row in by_id.items() if key.startswith(prefix)]
        statuses = [row["status"] for row in group]
        timeouts += sum(1 for status in statuses if status == "timeout")
        errors += sum(1 for status in statuses if status in {"error", "blocked_import"})
        if not group or any(row["status"] != "ok" for row in group):
            continue
        ok_profiles += 1
        values = [row["value"] for row in group]
        if any(outputs_differ(values[0], other, atol, rtol) for other in values[1:]):
            violated += 1
    output_changed = violated > 0
    if ok_profiles == 0:
        intensity = None
    else:
        intensity = violated / ok_profiles
    return {
        "task": task_id,
        "function": function_name,
        "attribute": attribute,
        "legitimate_use": label,
        "n_profiles_ok": ok_profiles,
        "n_profiles_violated": violated,
        "intensity": intensity,
        "output_changed": output_changed,
        "any_violation": output_changed and label == "invariant",
        "n_timeouts": timeouts,
        "n_errors": errors,
        "pairs": _pairs_for(attribute, profiles, by_id, atol, rtol),
    }


def _pairs_for(attribute, profiles, by_id, atol, rtol):
    pairs = []
    for index in range(len(profiles)):
        bases = [(key, row) for key, row in by_id.items() if key.startswith(f"{attribute}:{index}:base:")]
        follows = [(key, row) for key, row in by_id.items() if key.startswith(f"{attribute}:{index}:follow:")]
        if not bases:
            continue
        base_key, base_row = bases[0]
        base_value = base_key.split(":base:", 1)[1]
        for key, follow_row in follows:
            follow_value = key.split(":follow:", 1)[1]
            differed = (
                base_row["status"] == "ok"
                and follow_row["status"] == "ok"
                and outputs_differ(base_row["value"], follow_row["value"], atol, rtol)
            )
            pairs.append(
                {
                    "attribute": attribute,
                    "profile_index": index,
                    "base_value": base_value,
                    "follow_value": follow_value,
                    "base_status": base_row["status"],
                    "follow_status": follow_row["status"],
                    "base_output": base_row["value"],
                    "follow_output": follow_row["value"],
                    "differed": differed,
                }
            )
    return pairs


def _sanity_stats(by_id, profiles, sanity, atol):
    if sanity is None:
        return {"sanity_applicable": False, "sanity_n_ok": 0, "sanity_n_violations": 0}
    ok = 0
    violations = 0
    for index in range(len(profiles)):
        base = by_id.get(f"sanity:{index}:base")
        follow = by_id.get(f"sanity:{index}:follow")
        if not base or not follow or base["status"] != "ok" or follow["status"] != "ok":
            continue
        ok += 1
        if _sanity_violated(base["value"], follow["value"], sanity.kind, atol):
            violations += 1
    return {"sanity_applicable": True, "sanity_n_ok": ok, "sanity_n_violations": violations}


def _sanity_violated(before, after, kind: str, atol: float) -> bool:
    if kind == "bool_not_flip_false":
        return before is True and after is False
    if kind == "number_not_decrease":
        if isinstance(before, bool) or isinstance(after, bool):
            return False
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            return after < before - atol
        return False
    if kind == "number_not_increase":
        if isinstance(before, bool) or isinstance(after, bool):
            return False
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            return after > before + atol
        return False
    return False
