"""Full study runner. Append-only JSONL, safe to resume."""

from __future__ import annotations

import csv
import json
import subprocess
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import requests

from analysis.counterfactuals import build_profiles
from analysis.dynamic import score_function
from analysis.extract import extract_function
from analysis.metrics import (
    bootstrap_paired_diff,
    cbs_at_k,
    holm_reject,
    signflip_pvalue,
    wilson_interval,
)
from analysis.static_ast import KEYS, PROTECTED, PROXIES, analyze_source, static_csv_header
from models.base import get_adapter
from prompts.templates import render
from tasks.catalog import load_labels, load_tasks

FRESH_VARIANTS = ["terse", "detailed", "role", "mitigation_direct", "detailed_proxy"]
FOLLOW_VARIANTS = ["self_review", "feedback_repair"]


def generation_id(model_id: str, task_id: str, variant: str, sample_index: int) -> str:
    slug = model_id.replace("/", "_").replace(":", "-")
    return f"{slug}__{task_id}__{variant}__{sample_index}"


def planned_jobs(task_ids: Iterable[str], n_samples: int) -> List[dict]:
    jobs = []
    for task_id in task_ids:
        for sample_index in range(n_samples):
            for variant in FRESH_VARIANTS:
                jobs.append({"task": task_id, "variant": variant, "sample_index": sample_index})
            for variant in FOLLOW_VARIANTS:
                jobs.append({"task": task_id, "variant": variant, "sample_index": sample_index})
    return jobs


def model_order(models: List[dict]) -> List[dict]:
    enabled = [model for model in models if model.get("enabled", True)]
    local = [model for model in enabled if model["provider"] == "ollama"]
    remote = [model for model in enabled if model["provider"] != "ollama"]
    local.sort(key=lambda model: 0 if "llama" in model["model_id"] else 1)
    return local + remote


def load_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(record) + "\n")
        handle.flush()


def run_study(cfg: dict, root: Path, log) -> int:
    tasks = load_tasks(root / "tasks" / "tasks.yaml")
    labels = load_labels(root / "tasks" / "legitimate_use.csv")
    by_id = {task.id: task for task in tasks}
    profiles = build_profiles(cfg["n_profiles"], seed=cfg["seed"])
    out = root / "outputs"
    generations_path = out / "generations.jsonl"
    analysis_path = out / "analysis.jsonl"
    done_gen = {row["generation_id"]: row for row in load_jsonl(generations_path)}
    prior_analysis = load_jsonl(analysis_path)
    done_an = {row["generation_id"] for row in prior_analysis}
    reports = {}
    for row in prior_analysis:
        if row.get("variant") == "detailed":
            reports[row["generation_id"]] = _report_text(row)
    jobs = planned_jobs([task.id for task in tasks], cfg["n_samples"])
    ordered = model_order(cfg["models"])
    total = len(ordered) * len(jobs)
    finished = 0
    background_pulls = []
    log(f"planned_calls={total} already_generated={len(done_gen)}")
    for model_cfg in ordered:
        if model_cfg["provider"] == "ollama":
            stop_running_ollama()
            _wait_pulls(background_pulls, model_cfg["model_id"], log)
            log(f"pull {model_cfg['model_id']}")
            subprocess.run(["ollama", "pull", model_cfg["model_id"]], check=True)
            for later in ordered:
                if later["provider"] == "ollama" and later["model_id"] != model_cfg["model_id"]:
                    if not _ollama_present(later["model_id"]) and later["model_id"] not in {item[0] for item in background_pulls}:
                        log(f"background pull {later['model_id']}")
                        proc = subprocess.Popen(["ollama", "pull", later["model_id"]])
                        background_pulls.append((later["model_id"], proc))
        consecutive_errors = 0
        for job in jobs:
            finished += 1
            gid = generation_id(model_cfg["model_id"], job["task"], job["variant"], job["sample_index"])
            record = done_gen.get(gid)
            prior_attempts = int(record.get("attempts") or 1) if record and record.get("error") else 0
            fresh = False
            if record is not None and record.get("error") and prior_attempts < 2:
                record = None
            if record is None:
                fresh = True
                try:
                    record = _generate_one(cfg, model_cfg, by_id[job["task"]], job, done_gen, reports)
                    record["attempts"] = prior_attempts + 1
                except _DailyLimit as exc:
                    log(f"paused {exc}")
                    (out / "PAUSED.txt").write_text(str(exc) + "\n")
                    rebuild_outputs(out, cfg["n_samples"])
                    return 75
                except Exception as exc:  # noqa: BLE001 -- keep the run alive and record the failure
                    record = _error_record(gid, model_cfg, job, str(exc))
                    record["attempts"] = prior_attempts + 1
                    log(f"error {gid} {exc}")
                append_jsonl(generations_path, record)
                done_gen[gid] = record
                if model_cfg["provider"] != "ollama":
                    time.sleep(cfg.get("sleep_seconds", 0))
            if fresh or gid not in done_an:
                analyzed = _analyze(cfg, record, by_id[job["task"]], profiles, labels, out / "code")
                analyzed["from_error"] = bool(record.get("error"))
                append_jsonl(analysis_path, analyzed)
                done_an.add(gid)
                if record.get("variant") == "detailed":
                    reports[gid] = _report_text(analyzed)
            if record.get("error"):
                consecutive_errors += 1
                if consecutive_errors >= 5:
                    log("five consecutive errors, stopping this model")
                    break
            else:
                consecutive_errors = 0
            if finished % 10 == 0:
                log(f"progress {finished}/{total} last={gid}")
                rebuild_outputs(out, cfg["n_samples"])
        if model_cfg["provider"] == "ollama":
            stop_running_ollama()
        rebuild_outputs(out, cfg["n_samples"])
    rebuild_outputs(out, cfg["n_samples"])
    write_figures(out)
    write_report(out, root / "REPORT.md")
    log("study complete")
    return 0


class _DailyLimit(RuntimeError):
    pass


def _generate_one(cfg, model_cfg, task, job, done_gen, reports) -> dict:
    variant = job["variant"]
    sample_index = job["sample_index"]
    detailed_id = generation_id(model_cfg["model_id"], task.id, "detailed", sample_index)
    previous = ""
    report = "No invariant-attribute counterfactual violation was observed."
    if variant in FOLLOW_VARIANTS:
        detailed = done_gen.get(detailed_id)
        if detailed is None:
            raise RuntimeError(f"missing detailed generation {detailed_id}")
        previous = detailed.get("response") or ""
        if variant == "feedback_repair":
            report = reports.get(detailed_id, "The detailed sample has not been executed yet.")
    if variant == "self_review":
        prompt = render(task, variant, previous_code=previous)
    elif variant == "feedback_repair":
        prompt = render(task, variant, previous_code=previous, report=report)
    else:
        prompt = render(task, variant)
    adapter = get_adapter(
        {
            **model_cfg,
            "temperature": cfg["temperature"],
            "max_tokens": cfg["max_tokens"],
            "num_ctx_cap": cfg["num_ctx_cap"],
            "seed": cfg["seed"] + sample_index,
        }
    )
    started = time.perf_counter()
    try:
        text, meta = adapter.ask_with_meta([{"role": "user", "content": prompt}])
    except requests.HTTPError as exc:
        response = getattr(exc, "response", None)
        if response is not None and response.status_code == 429:
            retry_after = response.headers.get("retry-after", "")
            raise _DailyLimit(
                f"rate limit retry-after={retry_after or 'unknown'} on {model_cfg['model_id']}"
            ) from exc
        raise
    elapsed = time.perf_counter() - started
    code, reason = extract_function(text, task.id)
    return {
        "generation_id": generation_id(model_cfg["model_id"], task.id, variant, sample_index),
        "model": model_cfg["model_id"],
        "provider": model_cfg["provider"],
        "task": task.id,
        "variant": variant,
        "sample_index": sample_index,
        "seed": cfg["seed"] + sample_index,
        "temperature": cfg["temperature"],
        "elapsed_s": round(elapsed, 3),
        "prompt_eval_count": meta.get("prompt_eval_count"),
        "eval_count": meta.get("eval_count"),
        "num_ctx": meta.get("num_ctx"),
        "extract_ok": code is not None,
        "extract_reason": reason,
        "prompt": prompt,
        "response": text,
        "error": None,
    }


def _error_record(gid, model_cfg, job, message: str) -> dict:
    return {
        "generation_id": gid,
        "model": model_cfg["model_id"],
        "provider": model_cfg["provider"],
        "task": job["task"],
        "variant": job["variant"],
        "sample_index": job["sample_index"],
        "extract_ok": False,
        "extract_reason": "call_error",
        "prompt": "",
        "response": "",
        "error": message,
    }


def _report_text(row: dict) -> str:
    lines = []
    for item in row.get("dynamic") or []:
        if item.get("legitimate_use") != "invariant":
            continue
        if item.get("any_violation"):
            lines.append(
                f"{item['attribute']}: output changed on {item['n_profiles_violated']} of {item['n_profiles_ok']} profiles"
            )
    if not lines:
        return "No invariant-attribute counterfactual violation was observed."
    return "\n".join(lines)


def _ollama_present(model_id: str) -> bool:
    proc = subprocess.run(["ollama", "list"], capture_output=True, text=True, check=False)
    for line in proc.stdout.splitlines():
        name = line.split()[0] if line.split() else ""
        if name == model_id:
            return True
    return False


def _wait_pulls(pulls, model_id: str, log) -> None:
    still = []
    for name, proc in pulls:
        if name == model_id:
            log(f"waiting for pull {name}")
            proc.wait()
        else:
            still.append((name, proc))
    pulls[:] = still


def _latest(records: List[dict]) -> List[dict]:
    order = []
    by_id = {}
    for record in records:
        gid = record["generation_id"]
        if gid not in by_id:
            order.append(gid)
        by_id[gid] = record
    return [by_id[gid] for gid in order]


def _analyze(cfg, record, task, profiles, labels, code_dir: Path) -> dict:
    gid = record["generation_id"]
    code = None
    reason = record.get("extract_reason") or ""
    if record.get("response") and not record.get("error"):
        code, reason = extract_function(record["response"], task.id)
    static = {key: {"accessed": False, "control": False, "computation": False} for key in KEYS}
    dynamic = []
    if code:
        code_dir.mkdir(parents=True, exist_ok=True)
        (code_dir / f"{gid}.py").write_text(code)
        static = analyze_source(code, task.id)
        if record["variant"] == "detailed_proxy":
            used = {key: "proxy" for key in PROXIES}
        else:
            used = {key: labels[(task.id, key)].label for key in PROTECTED}
        dynamic = score_function(
            code,
            task.id,
            task.id,
            profiles,
            used,
            work_root=code_dir.parent,
            per_call_timeout_s=cfg["sandbox"]["per_call_timeout_s"],
            atol=cfg["atol"],
            rtol=cfg["rtol"],
            sanity=task.sanity,
        )
    pairs = []
    slim_dynamic = []
    for row in dynamic:
        for pair in row.pop("pairs", []):
            pair = dict(pair)
            pair["generation_id"] = gid
            pairs.append(pair)
        slim_dynamic.append(row)
    return {
        "generation_id": gid,
        "model": record["model"],
        "task": record["task"],
        "variant": record["variant"],
        "sample_index": record["sample_index"],
        "extract_ok": code is not None,
        "extract_reason": reason,
        "static": static,
        "dynamic": slim_dynamic,
        "pairs": pairs,
    }


def stop_running_ollama() -> None:
    proc = subprocess.run(["ollama", "ps"], capture_output=True, text=True, check=False)
    for line in proc.stdout.splitlines()[1:]:
        name = line.split()[0] if line.split() else ""
        if name and name != "NAME":
            subprocess.run(["ollama", "stop", name], check=False, capture_output=True)


def rebuild_outputs(out: Path, n_samples: int) -> None:
    records = _latest(load_jsonl(out / "analysis.jsonl"))
    _write_static(out / "static_analysis.csv", records)
    _write_dynamic(out / "dynamic_results.csv", records)
    _write_pairs(out / "dynamic_pairs.jsonl", records)
    _write_summary(out / "summary.csv", records, n_samples)


def _write_static(path: Path, records: List[dict]) -> None:
    header = static_csv_header()
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        for record in records:
            row = {
                "generation_id": record["generation_id"],
                "model": record["model"],
                "task": record["task"],
                "variant": record["variant"],
                "sample_index": record["sample_index"],
                "extract_ok": record["extract_ok"],
                "extract_reason": record.get("extract_reason") or "",
            }
            flags = record.get("static") or {}
            for key in KEYS:
                flag = flags.get(key) or {}
                row[f"{key}_accessed"] = bool(flag.get("accessed"))
                row[f"{key}_control"] = bool(flag.get("control"))
                row[f"{key}_computation"] = bool(flag.get("computation"))
            writer.writerow(row)


def _write_dynamic(path: Path, records: List[dict]) -> None:
    fields = [
        "generation_id", "model", "task", "variant", "attribute", "legitimate_use",
        "n_profiles_ok", "n_profiles_violated", "intensity", "output_changed",
        "any_violation", "n_timeouts", "n_errors", "limits_applied",
        "sanity_applicable", "sanity_n_ok", "sanity_n_violations",
    ]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            for item in record.get("dynamic") or []:
                writer.writerow({**item, "generation_id": record["generation_id"], "model": record["model"], "variant": record["variant"]})


def _write_pairs(path: Path, records: List[dict]) -> None:
    with path.open("w") as handle:
        for record in records:
            for pair in record.get("pairs") or []:
                handle.write(json.dumps(pair) + "\n")


def _write_summary(path: Path, records: List[dict], n_samples: int) -> None:
    groups: Dict[tuple, List[dict]] = {}
    for record in records:
        groups.setdefault((record["model"], record["task"], record["variant"]), []).append(record)
    rows = []
    attributes = list(PROTECTED) + list(PROXIES)
    pooled: Dict[tuple, List[dict]] = {}
    for (model, task, variant), members in groups.items():
        for attribute in attributes:
            rows.append(_summary_row(model, task, variant, attribute, members, n_samples))
        pooled.setdefault((model, variant), []).extend(members)
    for (model, variant), members in pooled.items():
        for attribute in attributes:
            rows.append(_summary_row(model, "ALL", variant, attribute, members, n_samples))
    fields = list(rows[0].keys()) if rows else ["model"]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _summary_row(model, task, variant, attribute, members, n_samples) -> dict:
    extracted = [record for record in members if record.get("extract_ok")]
    dynamic_rows = []
    for record in members:
        for item in record.get("dynamic") or []:
            if item.get("attribute") == attribute:
                dynamic_rows.append(item)
    executable = [item for item in dynamic_rows if (item.get("n_profiles_ok") or 0) > 0]
    violations = [item for item in executable if item.get("any_violation")]
    changed = [item for item in executable if item.get("output_changed")]
    accessed = 0
    control = 0
    computation = 0
    for record in extracted:
        flag = (record.get("static") or {}).get(attribute) or {}
        accessed += int(bool(flag.get("accessed")))
        control += int(bool(flag.get("control")))
        computation += int(bool(flag.get("computation")))
    n = len(members)
    n_ex = len(extracted)
    n_run = len(executable)
    k_bias = len(violations)
    low, high = wilson_interval(k_bias, n_run) if n_run else (None, None)
    intensities = [item["intensity"] for item in executable if item.get("intensity") is not None]
    viol_int = [item["intensity"] for item in violations if item.get("intensity") is not None]
    biased_by_sample = _cbs_prompts(members, attribute, n_samples, task)
    cbs = None
    if biased_by_sample is not None:
        try:
            cbs = cbs_at_k(biased_by_sample, n_samples)
        except ValueError:
            cbs = None
    return {
        "model": model,
        "task": task,
        "variant": variant,
        "attribute": attribute,
        "n_samples": n,
        "n_extracted": n_ex,
        "n_executable": n_run,
        "extraction_rate": n_ex / n if n else None,
        "execution_success_rate": n_run / n if n else None,
        "static_accessed_rate": accessed / n_ex if n_ex else None,
        "static_control_rate": control / n_ex if n_ex else None,
        "static_computation_rate": computation / n_ex if n_ex else None,
        "dynamic_bias_rate": k_bias / n_run if n_run else None,
        "wilson_low": low,
        "wilson_high": high,
        "output_changed_rate": len(changed) / n_run if n_run else None,
        "mean_intensity_all": sum(intensities) / len(intensities) if intensities else None,
        "mean_intensity_violators": sum(viol_int) / len(viol_int) if viol_int else None,
        "cbs": None if cbs is None else cbs["cbs"],
        "cbs_u": None if cbs is None else cbs["cbs_u"],
        "cbs_i": None if cbs is None else cbs["cbs_i"],
    }


def _cbs_prompts(members, attribute, n_samples, task):
    if task != "ALL":
        return _biased_flags(members, attribute, n_samples)
    by_task: Dict[str, List[dict]] = {}
    for record in members:
        by_task.setdefault(record["task"], []).append(record)
    prompts = []
    for task_id in sorted(by_task):
        one = _biased_flags(by_task[task_id], attribute, n_samples)
        if one is None:
            return None
        prompts.append(one[0])
    return prompts


def _biased_flags(members, attribute, n_samples):
    by_sample = {}
    for record in members:
        flag = None
        for item in record.get("dynamic") or []:
            if item.get("attribute") == attribute:
                if (item.get("n_profiles_ok") or 0) == 0:
                    flag = None
                else:
                    flag = bool(item.get("any_violation"))
        by_sample[record["sample_index"]] = flag
    if any(index not in by_sample for index in range(n_samples)):
        return None
    return [[by_sample[index] for index in range(n_samples)]]


def write_figures(out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = list(csv.DictReader((out / "summary.csv").open()))
    fig_dir = out / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    _bar_attribute_model(plt, rows, fig_dir / "bias_by_attribute_model.png")
    _bar_mitigation(plt, rows, fig_dir / "mitigation_before_after.png")
    _agreement_matrix(plt, _latest(load_jsonl(out / "analysis.jsonl")), fig_dir / "static_dynamic_agreement.png")


def _f(value: Optional[str]) -> Optional[float]:
    if value in (None, "", "None"):
        return None
    return float(value)


def _bar_attribute_model(plt, rows, path: Path) -> None:
    selected = [
        row for row in rows
        if row["task"] == "ALL" and row["variant"] == "detailed" and row["attribute"] in PROTECTED
    ]
    models = sorted({row["model"] for row in selected})
    if not models:
        return
    import numpy as np

    x = np.arange(len(PROTECTED))
    width = 0.8 / max(1, len(models))
    fig, ax = plt.subplots(figsize=(10, 5))
    for index, model in enumerate(models):
        heights = []
        for attribute in PROTECTED:
            match = [row for row in selected if row["model"] == model and row["attribute"] == attribute]
            heights.append(0 if not match or _f(match[0]["dynamic_bias_rate"]) is None else _f(match[0]["dynamic_bias_rate"]))
        ax.bar(x + index * width, heights, width, label=model)
    ax.set_xticks(x + width * (len(models) - 1) / 2)
    ax.set_xticklabels(PROTECTED, rotation=30, ha="right")
    ax.set_ylabel("Dynamic bias rate")
    ax.set_title("Detailed prompts, invariant attributes")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _bar_mitigation(plt, rows, path: Path) -> None:
    variants = ["detailed", "mitigation_direct", "self_review", "feedback_repair"]
    selected = [row for row in rows if row["task"] == "ALL" and row["variant"] in variants and row["attribute"] == "gender"]
    # Gender is one attribute. Overall rate is computed in the report. This figure uses the
    # mean of per-attribute dynamic bias rates so one chart is not dominated by a single attribute.
    models = sorted({row["model"] for row in rows if row["task"] == "ALL"})
    if not models:
        return
    import numpy as np

    x = np.arange(len(variants))
    width = 0.8 / max(1, len(models))
    fig, ax = plt.subplots(figsize=(10, 5))
    for index, model in enumerate(models):
        heights = []
        for variant in variants:
            cells = [
                _f(row["dynamic_bias_rate"])
                for row in rows
                if row["model"] == model and row["task"] == "ALL" and row["variant"] == variant and row["attribute"] in PROTECTED
            ]
            cells = [value for value in cells if value is not None]
            heights.append(sum(cells) / len(cells) if cells else 0)
        ax.bar(x + index * width, heights, width, label=model)
    ax.set_xticks(x + width * (len(models) - 1) / 2)
    ax.set_xticklabels(variants, rotation=20, ha="right")
    ax.set_ylabel("Mean dynamic bias rate across protected attributes")
    ax.set_title("Before and after prompt mitigation")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    del selected


def _agreement_matrix(plt, records, path: Path) -> None:
    matrix = {"yy": 0, "yn": 0, "ny": 0, "nn": 0}
    for record in records:
        if record.get("variant") != "detailed":
            continue
        flags = record.get("static") or {}
        for item in record.get("dynamic") or []:
            if item.get("legitimate_use") != "invariant":
                continue
            if (item.get("n_profiles_ok") or 0) == 0:
                continue
            used = bool((flags.get(item["attribute"]) or {}).get("accessed"))
            violated = bool(item.get("any_violation"))
            if used and violated:
                matrix["yy"] += 1
            elif used:
                matrix["yn"] += 1
            elif violated:
                matrix["ny"] += 1
            else:
                matrix["nn"] += 1
    import numpy as np

    grid = np.array([[matrix["yy"], matrix["yn"]], [matrix["ny"], matrix["nn"]]], dtype=float)
    fig, ax = plt.subplots(figsize=(5, 4))
    image = ax.imshow(grid, cmap="Blues")
    ax.set_xticks([0, 1], ["dynamic yes", "dynamic no"])
    ax.set_yticks([0, 1], ["static yes", "static no"])
    for i in range(2):
        for j in range(2):
            ax.text(j, i, str(int(grid[i, j])), ha="center", va="center")
    ax.set_title("Static use vs dynamic violation")
    fig.colorbar(image)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def write_report(out: Path, path: Path) -> None:
    records = _latest(load_jsonl(out / "analysis.jsonl"))
    if not records:
        path.write_text("# Report\n\nNo analyzed generations yet.\n")
        return
    lines = ["# Report", "", "Numbers below are computed from `outputs/analysis.jsonl`. Duplicate generation ids keep the last record.", ""]
    lines.append(f"Analyzed generations: {len(records)}.")
    lines.append("")
    lines.extend(_overall_lines(records))
    lines.append("")
    lines.extend(_mitigation_lines(records))
    lines.append("")
    lines.extend(_proxy_lines(records))
    lines.append("")
    lines.extend(_sanity_lines(records))
    lines.append("")
    lines.append("## Limits")
    lines.append("")
    lines.append("Profiles are synthetic. The data-flow scan misses computed keys and nested helpers. Legitimate-use labels follow `tasks/legitimate_use.csv`. Credit × age is excluded from the bias numerator. Proxy differences are logged and are not scored as bias. This run uses small local models plus one Groq model, not the frontier models in Huang et al. CBS here is the share of executable samples whose output changes on an invariant attribute. A sample that does not run counts as not biased in CBS_U and CBS_I, and it is outside the dynamic-bias denominator.")
    path.write_text("\n".join(lines) + "\n")


def _overall_lines(records: List[dict]) -> List[str]:
    lines = ["## Dynamic bias by model", ""]
    models = sorted({record["model"] for record in records})
    for model in models:
        subset = [record for record in records if record["model"] == model and record["variant"] == "detailed"]
        rate, n_run, k = _overall_rate(subset)
        low, high = wilson_interval(k, n_run) if n_run else (None, None)
        lines.append(
            f"- `{model}` detailed, any invariant attribute: {k}/{n_run} = {_fmt(rate)} "
            f"(Wilson 95% {_fmt(low)} to {_fmt(high)})."
        )
    return lines


def _overall_rate(records: List[dict]):
    executable = 0
    biased = 0
    for record in records:
        flags = []
        for item in record.get("dynamic") or []:
            if item.get("legitimate_use") != "invariant":
                continue
            if (item.get("n_profiles_ok") or 0) == 0:
                continue
            flags.append(bool(item.get("any_violation")))
        if not flags:
            continue
        executable += 1
        biased += int(any(flags))
    rate = biased / executable if executable else None
    return rate, executable, biased


def _mitigation_lines(records: List[dict]) -> List[str]:
    lines = [
        "## Mitigation contrasts",
        "",
        "Each number is the mean paired change in task-level bias rate, after minus before. A negative change is a lower bias rate after the prompt change. Within each model, Holm at 0.05 covers the overall direct-mitigation contrast, the six protected-attribute direct-mitigation contrasts, and the overall feedback-repair contrast. Self-review is outside that family.",
        "",
    ]
    models = sorted({record["model"] for record in records})
    for model in models:
        family = []
        notes = []
        overall = _contrast(records, model, "detailed", "mitigation_direct", None)
        family.append(("direct mitigation, any invariant attribute", overall))
        for attribute in PROTECTED:
            family.append((f"direct mitigation, {attribute}", _contrast(records, model, "detailed", "mitigation_direct", attribute)))
        family.append(("feedback repair, any invariant attribute", _contrast(records, model, "detailed", "feedback_repair", None)))
        notes.append(("self-review, any invariant attribute", _contrast(records, model, "detailed", "self_review", None)))
        usable = [(label, result) for label, result in family if result is not None]
        rejected = holm_reject([result["p"] for _, result in usable], alpha=0.05) if usable else []
        lines.append(f"### `{model}`")
        lines.append("")
        for (label, result), keep in zip(usable, rejected):
            lines.append(_contrast_sentence(label, result, rejected=keep))
        skipped = [label for label, result in family if result is None]
        if skipped:
            lines.append("Not enough paired tasks for: " + "; ".join(skipped) + ".")
        for label, result in notes:
            if result is None:
                lines.append(f"- {label}: not enough paired tasks. This contrast is outside the Holm family.")
            else:
                lines.append(_contrast_sentence(label, result, rejected=None))
        lines.append("")
    return lines


def _contrast(records, model, before_variant, after_variant, attribute):
    if attribute is None:
        before, after = _paired_overall(records, model, before_variant, after_variant)
    else:
        before, after = _paired_attribute(records, model, before_variant, after_variant, attribute)
    if len(before) < 2:
        return None
    low, high = bootstrap_paired_diff(before, after, n_boot=10000, seed=42)
    p_value = signflip_pvalue(before, after, n_perm=10000, seed=42)
    delta = sum(after[i] - before[i] for i in range(len(before))) / len(before)
    return {"delta": delta, "low": low, "high": high, "p": p_value, "n": len(before)}


def _contrast_sentence(label, result, rejected) -> str:
    holm = ""
    if rejected is True:
        holm = " Holm rejects this contrast."
    elif rejected is False:
        holm = " Holm does not reject this contrast."
    else:
        holm = " Outside the Holm family."
    return (
        f"- {label}: change {result['delta']:.4f} across {result['n']} tasks, "
        f"bootstrap 95% {result['low']:.4f} to {result['high']:.4f}, "
        f"sign-flip p={result['p']:.4f}.{holm}"
    )


def _proxy_lines(records: List[dict]) -> List[str]:
    lines = ["## Proxy prompts", "", "These rates count an output change. They are not bias rates and they are outside the Holm family.", ""]
    models = sorted({record["model"] for record in records})
    for model in models:
        subset = [record for record in records if record["model"] == model and record["variant"] == "detailed_proxy"]
        executable = 0
        changed = 0
        for record in subset:
            flags = []
            for item in record.get("dynamic") or []:
                if item.get("attribute") not in PROXIES:
                    continue
                if (item.get("n_profiles_ok") or 0) == 0:
                    continue
                flags.append(bool(item.get("output_changed")))
            if not flags:
                continue
            executable += 1
            changed += int(any(flags))
        rate = changed / executable if executable else None
        low, high = wilson_interval(changed, executable) if executable else (None, None)
        lines.append(
            f"- `{model}`: {changed}/{executable} executable proxy samples changed on at least one proxy "
            f"({_fmt(rate)}, Wilson 95% {_fmt(low)} to {_fmt(high)})."
        )
    return lines


def _sanity_lines(records: List[dict]) -> List[str]:
    lines = ["## Sanity checks on legitimate features", ""]
    models = sorted({record["model"] for record in records})
    for model in models:
        subset = [record for record in records if record["model"] == model and record["variant"] == "detailed"]
        applicable = 0
        violated = 0
        for record in subset:
            rows = record.get("dynamic") or []
            if not rows or not rows[0].get("sanity_applicable"):
                continue
            if not rows[0].get("sanity_n_ok"):
                continue
            applicable += 1
            violated += int((rows[0].get("sanity_n_violations") or 0) > 0)
        rate = violated / applicable if applicable else None
        lines.append(
            f"- `{model}` detailed: {violated}/{applicable} executable functions broke a sanity relation ({_fmt(rate)})."
        )
    return lines


def _paired_overall(records, model, before_variant, after_variant):
    def task_rate(variant):
        grouped: Dict[str, List[dict]] = {}
        for record in records:
            if record["model"] == model and record["variant"] == variant:
                grouped.setdefault(record["task"], []).append(record)
        rates = {}
        for task, members in grouped.items():
            rate, n_run, _k = _overall_rate(members)
            if n_run:
                rates[task] = rate
        return rates

    before_rates = task_rate(before_variant)
    after_rates = task_rate(after_variant)
    keys = sorted(set(before_rates) & set(after_rates))
    return [before_rates[key] for key in keys], [after_rates[key] for key in keys]


def _paired_attribute(records, model, before_variant, after_variant, attribute):
    def task_rate(variant):
        grouped: Dict[str, List[dict]] = {}
        for record in records:
            if record["model"] == model and record["variant"] == variant:
                grouped.setdefault(record["task"], []).append(record)
        rates = {}
        for task, members in grouped.items():
            executable = 0
            violations = 0
            for record in members:
                for item in record.get("dynamic") or []:
                    if item.get("attribute") != attribute or item.get("legitimate_use") != "invariant":
                        continue
                    if (item.get("n_profiles_ok") or 0) == 0:
                        continue
                    executable += 1
                    violations += int(bool(item.get("any_violation")))
            if executable:
                rates[task] = violations / executable
        return rates

    before_rates = task_rate(before_variant)
    after_rates = task_rate(after_variant)
    keys = sorted(set(before_rates) & set(after_rates))
    return [before_rates[key] for key in keys], [after_rates[key] for key in keys]


def _fmt(value) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4f}"
