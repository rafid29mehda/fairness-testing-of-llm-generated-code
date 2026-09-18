"""Entry point.

python run.py loads the config and exits. It does not call a model.
python run.py --pilot makes one local call and writes that sample under outputs/.
python run.py --e2e makes seven Groq calls on loan_eligibility and writes outputs/e2e/.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent


def load_config(path: Path | None = None) -> dict:
    config_path = Path(path) if path is not None else ROOT / "config.yaml"
    with config_path.open() as handle:
        return yaml.safe_load(handle)


def check(cfg: dict) -> str:
    from tasks.catalog import load_labels, load_tasks

    tasks = load_tasks(ROOT / "tasks" / "tasks.yaml")
    labels = load_labels(ROOT / "tasks" / "legitimate_use.csv")
    cautious = sum(1 for label in labels.values() if label.label == "may_legitimately_differ")
    lines = [
        f"tasks={len(tasks)}",
        f"labels={len(labels)}",
        f"may_legitimately_differ={cautious}",
        f"models={len(cfg['models'])}",
        f"temperature={cfg['temperature']}",
        f"n_samples={cfg['n_samples']}",
        f"num_ctx_cap={cfg['num_ctx_cap']}",
        "generation=off",
    ]
    return "\n".join(lines)


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def pilot(cfg: dict, model_id: str) -> int:
    """One task, one sample, one local model. Writes only what that call produced."""
    from analysis.counterfactuals import build_profiles
    from analysis.dynamic import score_function
    from analysis.extract import extract_function
    from analysis.static_ast import KEYS, analyze_source, static_csv_header
    from models.base import get_adapter
    from prompts.templates import render
    from tasks.catalog import load_labels, load_tasks

    load_dotenv(ROOT / ".env")
    tasks = load_tasks(ROOT / "tasks" / "tasks.yaml")
    task = next(item for item in tasks if item.id == "loan_eligibility")
    labels = load_labels(ROOT / "tasks" / "legitimate_use.csv")
    task_labels = {attr: labels[(task.id, attr)].label for attr in (
        "gender", "race_ethnicity", "age", "religion", "disability", "marital_status"
    )}
    prompt = render(task, "detailed")
    adapter = get_adapter(
        {
            "provider": "ollama",
            "name": "Llama 3.2 3B",
            "model_id": model_id,
            "temperature": cfg["temperature"],
            "max_tokens": cfg["max_tokens"],
            "num_ctx_cap": cfg["num_ctx_cap"],
            "seed": cfg["seed"],
        }
    )
    started = time.perf_counter()
    text, meta = adapter.ask_with_meta([{"role": "user", "content": prompt}])
    elapsed = time.perf_counter() - started
    code, reason = extract_function(text, task.id)
    out_dir = ROOT / "outputs"
    code_dir = out_dir / "code"
    code_dir.mkdir(parents=True, exist_ok=True)
    generation_id = f"pilot-{model_id.replace(':', '-')}-loan_eligibility-detailed-0"
    record = {
        "generation_id": generation_id,
        "model": model_id,
        "task": task.id,
        "variant": "detailed",
        "sample_index": 0,
        "elapsed_s": round(elapsed, 3),
        "prompt_eval_count": meta.get("prompt_eval_count"),
        "eval_count": meta.get("eval_count"),
        "num_ctx": meta.get("num_ctx"),
        "extract_ok": code is not None,
        "extract_reason": reason,
        "prompt": prompt,
        "response": text,
    }
    with (out_dir / "generations.jsonl").open("w") as handle:
        handle.write(json.dumps(record) + "\n")
    flags = {key: {"accessed": False, "control": False, "computation": False} for key in KEYS}
    if code is not None:
        (code_dir / f"{generation_id}.py").write_text(code)
        flags = analyze_source(code, task.id)
        profiles = build_profiles(cfg["n_profiles"], seed=cfg["seed"])
        rows = score_function(
            code,
            task.id,
            task.id,
            profiles,
            task_labels,
            work_root=out_dir,
            per_call_timeout_s=cfg["sandbox"]["per_call_timeout_s"],
            atol=cfg["atol"],
            rtol=cfg["rtol"],
        )
    else:
        rows = []
    header = static_csv_header()
    static_row = {
        "generation_id": generation_id,
        "model": model_id,
        "task": task.id,
        "variant": "detailed",
        "sample_index": 0,
        "extract_ok": code is not None,
        "extract_reason": reason,
    }
    for key in KEYS:
        static_row[f"{key}_accessed"] = flags[key]["accessed"]
        static_row[f"{key}_control"] = flags[key]["control"]
        static_row[f"{key}_computation"] = flags[key]["computation"]
    with (out_dir / "static_analysis.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerow(static_row)
    dynamic_fields = [
        "generation_id", "model", "task", "variant", "attribute", "legitimate_use",
        "n_profiles_ok", "n_profiles_violated", "intensity", "output_changed",
        "any_violation", "n_timeouts", "n_errors", "limits_applied",
    ]
    with (out_dir / "dynamic_results.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=dynamic_fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "generation_id": generation_id,
                    "model": model_id,
                    "task": task.id,
                    "variant": "detailed",
                    "attribute": row["attribute"],
                    "legitimate_use": row["legitimate_use"],
                    "n_profiles_ok": row["n_profiles_ok"],
                    "n_profiles_violated": row["n_profiles_violated"],
                    "intensity": row["intensity"],
                    "output_changed": row["output_changed"],
                    "any_violation": row["any_violation"],
                    "n_timeouts": row["n_timeouts"],
                    "n_errors": row["n_errors"],
                    "limits_applied": row.get("limits_applied", ""),
                }
            )
    print(json.dumps({
        "generation_id": generation_id,
        "elapsed_s": record["elapsed_s"],
        "prompt_eval_count": record["prompt_eval_count"],
        "eval_count": record["eval_count"],
        "num_ctx": record["num_ctx"],
        "extract_ok": record["extract_ok"],
        "extract_reason": record["extract_reason"],
        "dynamic_rows": len(rows),
    }, indent=2))
    return 0 if record["extract_ok"] else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fairness testing of LLM-generated code")
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Load config, tasks, and labels, then exit. This is the default.",
    )
    parser.add_argument(
        "--pilot",
        action="store_true",
        help="One local sample of loan_eligibility. Does not start the full run.",
    )
    parser.add_argument("--pilot-model", default="llama3.2:latest")
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Run the full study. Resumes from outputs/generations.jsonl.",
    )
    parser.add_argument(
        "--e2e",
        action="store_true",
        help="Seven Groq calls on loan_eligibility. Writes outputs/e2e/ and does not load a local model.",
    )
    args = parser.parse_args(argv)
    if args.e2e and args.generate:
        print("Pass only one of --e2e or --generate.")
        return 2
    cfg = load_config(args.config)
    if args.e2e:
        load_dotenv(ROOT / ".env")
        from analysis.e2e import run_e2e

        def log(message: str) -> None:
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            line = f"{stamp} {message}"
            print(line, flush=True)
            log_path = ROOT / "outputs" / "e2e" / "run.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a") as handle:
                handle.write(line + "\n")

        return run_e2e(cfg, ROOT, log)
    if args.generate:
        load_dotenv(ROOT / ".env")
        from analysis.study import run_study

        def log(message: str) -> None:
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            line = f"{stamp} {message}"
            print(line, flush=True)
            log_path = ROOT / "outputs" / "run.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a") as handle:
                handle.write(line + "\n")

        return run_study(cfg, ROOT, log)
    if args.pilot:
        return pilot(cfg, args.pilot_model)
    print(check(cfg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
