"""Short Groq run: one task, one sample, every prompt variant. Does not load a local model."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from analysis.counterfactuals import build_profiles
from analysis.study import (
    _DailyLimit,
    _analyze,
    _error_record,
    _generate_one,
    _report_text,
    append_jsonl,
    generation_id,
    load_jsonl,
    planned_jobs,
    rebuild_outputs,
)
from tasks.catalog import load_labels, load_tasks

E2E_TASK = "loan_eligibility"
E2E_MODEL_ID = "openai/gpt-oss-20b"
E2E_BASE_URL = "https://api.groq.com/openai/v1"
E2E_API_KEY_ENV = "GROQ_API_KEY"
E2E_CALLS = 7


def e2e_jobs() -> List[dict]:
    return planned_jobs([E2E_TASK], 1)


def select_e2e_model(models: List[dict]) -> Optional[dict]:
    matches = [
        model
        for model in models
        if model.get("enabled", True)
        and model.get("provider") == "openai_compat"
        and model.get("model_id") == E2E_MODEL_ID
        and model.get("base_url") == E2E_BASE_URL
        and model.get("api_key_env") == E2E_API_KEY_ENV
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def write_manifest(out: Path, seed: int, analyses: Sequence[Dict]) -> bool:
    if len(analyses) != E2E_CALLS:
        return False
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": E2E_MODEL_ID,
        "task": E2E_TASK,
        "seed": seed,
        "n_calls": E2E_CALLS,
        "generation_ids": [row["generation_id"] for row in analyses],
        "n_extracted": sum(1 for row in analyses if row.get("extract_ok")),
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (out / "manifest.json").write_text(json.dumps(payload, indent=2) + "\n")
    return True


def write_paused(out: Path, message: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "PAUSED.txt").write_text(message + "\n")


def _scoring_failure(record: dict, message: str) -> dict:
    return {
        "generation_id": record["generation_id"],
        "model": record.get("model"),
        "task": record.get("task"),
        "variant": record.get("variant"),
        "sample_index": record.get("sample_index"),
        "extract_ok": False,
        "extract_reason": "scoring_failure",
        "scoring_error": message,
        "static": {},
        "dynamic": [],
        "pairs": [],
        "from_error": True,
    }


def _later_generation_needed(jobs, start_index: int, done_gen: dict, model_id: str) -> bool:
    for job in jobs[start_index + 1 :]:
        gid = generation_id(model_id, job["task"], job["variant"], job["sample_index"])
        if gid not in done_gen:
            return True
    return False


def run_e2e(cfg: dict, root: Path, log) -> int:
    out = root / "outputs" / "e2e"
    if (out / "manifest.json").exists():
        log("e2e manifest already present")
        return 0
    model_cfg = select_e2e_model(cfg.get("models") or [])
    if model_cfg is None:
        log("Groq model for the e2e run is missing or disabled")
        return 2
    # Proof stops on the first 429; the full study keeps the default of 5 retries.
    model_cfg = {**model_cfg, "max_retries": 1}
    tasks = load_tasks(root / "tasks" / "tasks.yaml")
    labels = load_labels(root / "tasks" / "legitimate_use.csv")
    by_id = {task.id: task for task in tasks}
    profiles = build_profiles(cfg["n_profiles"], seed=cfg["seed"])
    out.mkdir(parents=True, exist_ok=True)
    generations_path = out / "generations.jsonl"
    analysis_path = out / "analysis.jsonl"
    done_gen = {row["generation_id"]: row for row in load_jsonl(generations_path)}
    prior_analysis = load_jsonl(analysis_path)
    done_an = {row["generation_id"] for row in prior_analysis}
    reports = {}
    for row in prior_analysis:
        if row.get("variant") == "detailed" and row.get("extract_reason") != "scoring_failure":
            reports[row["generation_id"]] = _report_text(row)
    jobs = e2e_jobs()
    consecutive_errors = 0
    for index, job in enumerate(jobs):
        gid = generation_id(model_cfg["model_id"], job["task"], job["variant"], job["sample_index"])
        record = done_gen.get(gid)
        made_network_call = False
        if record is None:
            made_network_call = True
            try:
                record = _generate_one(cfg, model_cfg, by_id[job["task"]], job, done_gen, reports)
                record["attempts"] = 1
            except _DailyLimit as exc:
                write_paused(out, str(exc))
                log(f"paused {exc}")
                return 75
            except Exception as exc:  # noqa: BLE001 -- store the call and keep going
                record = _error_record(gid, model_cfg, job, str(exc))
                record["attempts"] = 1
                log(f"error {gid} {exc}")
            append_jsonl(generations_path, record)
            done_gen[gid] = record
        if gid not in done_an:
            try:
                analyzed = _analyze(cfg, record, by_id[job["task"]], profiles, labels, out / "code")
                analyzed["from_error"] = bool(record.get("error"))
            except Exception as exc:  # noqa: BLE001 -- store scoring failure, withhold manifest until 7 exist
                analyzed = _scoring_failure(record, str(exc))
                log(f"scoring failure {gid} {exc}")
            append_jsonl(analysis_path, analyzed)
            done_an.add(gid)
            if record.get("variant") == "detailed" and analyzed.get("extract_reason") != "scoring_failure":
                reports[gid] = _report_text(analyzed)
        if record.get("error"):
            consecutive_errors += 1
            if consecutive_errors >= 5:
                write_paused(out, "five consecutive errors")
                log("five consecutive errors")
                return 75
        else:
            consecutive_errors = 0
        if made_network_call and _later_generation_needed(jobs, index, done_gen, model_cfg["model_id"]):
            time.sleep(cfg.get("sleep_seconds", 0))
    analyses = load_jsonl(analysis_path)
    if len(analyses) != E2E_CALLS:
        log("e2e run incomplete")
        return 75
    rebuild_outputs(out, 1)
    write_manifest(out, cfg["seed"], analyses)
    log("e2e run finished")
    return 0
