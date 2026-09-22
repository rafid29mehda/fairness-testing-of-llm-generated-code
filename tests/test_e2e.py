import json
from pathlib import Path

from analysis.e2e import (
    E2E_CALLS,
    E2E_MODEL_ID,
    E2E_TASK,
    e2e_jobs,
    select_e2e_model,
    write_manifest,
    write_paused,
)
from analysis.study import generation_id

VARIANTS = [
    "terse",
    "detailed",
    "role",
    "mitigation_direct",
    "detailed_proxy",
    "self_review",
    "feedback_repair",
]


def test_e2e_jobs_are_one_task_one_sample_every_variant():
    jobs = e2e_jobs()
    assert len(jobs) == E2E_CALLS == 7
    assert [job["variant"] for job in jobs] == VARIANTS
    assert {job["task"] for job in jobs} == {E2E_TASK}
    assert {job["sample_index"] for job in jobs} == {0}
    ids = {
        generation_id(E2E_MODEL_ID, job["task"], job["variant"], job["sample_index"])
        for job in jobs
    }
    assert len(ids) == 7


def test_select_e2e_model_keeps_only_the_groq_entry():
    models = [
        {"provider": "ollama", "model_id": "llama3.2:3b", "enabled": True},
        {"provider": "ollama", "model_id": "qwen2.5-coder:7b", "enabled": True},
        {
            "provider": "openai_compat",
            "model_id": E2E_MODEL_ID,
            "enabled": True,
            "base_url": "https://api.groq.com/openai/v1",
            "api_key_env": "GROQ_API_KEY",
        },
    ]
    chosen = select_e2e_model(models)
    assert chosen["model_id"] == E2E_MODEL_ID
    assert chosen["provider"] == "openai_compat"


def test_select_e2e_model_rejects_a_disabled_groq_entry():
    models = [
        {
            "provider": "openai_compat",
            "model_id": E2E_MODEL_ID,
            "enabled": False,
            "base_url": "https://api.groq.com/openai/v1",
            "api_key_env": "GROQ_API_KEY",
        }
    ]
    assert select_e2e_model(models) is None


def test_select_e2e_model_rejects_a_wrong_base_url():
    models = [
        {
            "provider": "openai_compat",
            "model_id": E2E_MODEL_ID,
            "enabled": True,
            "base_url": "https://api.example.com/v1",
            "api_key_env": "GROQ_API_KEY",
        }
    ]
    assert select_e2e_model(models) is None


def test_select_e2e_model_rejects_two_matching_entries():
    entry = {
        "provider": "openai_compat",
        "model_id": E2E_MODEL_ID,
        "enabled": True,
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
    }
    assert select_e2e_model([entry, dict(entry)]) is None


def _analysis(index: int, extract_ok: bool = True) -> dict:
    return {
        "generation_id": f"id-{index}",
        "extract_ok": extract_ok,
        "task": "loan_eligibility",
        "variant": "detailed",
        "sample_index": 0,
    }


def test_manifest_is_written_only_for_seven_analysis_records(tmp_path: Path):
    short = tmp_path / "short"
    assert write_manifest(short, seed=42, analyses=[_analysis(i) for i in range(6)]) is False
    assert not (short / "manifest.json").exists()

    full = tmp_path / "full"
    records = [_analysis(i, extract_ok=(i != 0)) for i in range(7)]
    assert write_manifest(full, seed=42, analyses=records) is True
    manifest = json.loads((full / "manifest.json").read_text())
    assert manifest["model"] == "openai/gpt-oss-20b"
    assert manifest["task"] == "loan_eligibility"
    assert manifest["seed"] == 42
    assert manifest["n_calls"] == 7
    assert manifest["generation_ids"] == [f"id-{i}" for i in range(7)]
    assert manifest["n_extracted"] == 6
    assert "finished_at" in manifest


def test_paused_file_does_not_create_a_manifest(tmp_path: Path):
    write_paused(tmp_path, "rate limit")
    assert (tmp_path / "PAUSED.txt").read_text() == "rate limit\n"
    assert not (tmp_path / "manifest.json").exists()


import requests

from analysis.e2e import run_e2e


class FakeAdapter:
    def __init__(self):
        self.calls = 0

    def ask_with_meta(self, messages):
        self.calls += 1
        text = "def loan_eligibility(person):\n    return person['income'] > 0\n"
        return text, {"prompt_eval_count": 10, "eval_count": 8, "num_ctx": None}


def _cfg():
    return {
        "seed": 42,
        "temperature": 0.8,
        "max_tokens": 800,
        "num_ctx_cap": 4096,
        "sleep_seconds": 12,
        "n_profiles": 24,
        "atol": 1e-9,
        "rtol": 0.0,
        "n_samples": 5,
        "sandbox": {"per_call_timeout_s": 2},
        "models": [
            {"provider": "ollama", "model_id": "llama3.2:3b", "enabled": True, "name": "Llama"},
            {
                "provider": "openai_compat",
                "name": "GPT-OSS 20B",
                "model_id": "openai/gpt-oss-20b",
                "base_url": "https://api.groq.com/openai/v1",
                "api_key_env": "GROQ_API_KEY",
                "enabled": True,
            },
        ],
    }


def test_run_e2e_writes_seven_records_and_does_not_open_the_study_log(tmp_path: Path, monkeypatch):
    study = tmp_path / "outputs"
    study.mkdir()
    (study / "generations.jsonl").write_text("{not json\n")
    repo = Path(__file__).resolve().parents[1]
    (tmp_path / "tasks").symlink_to(repo / "tasks")
    adapter = FakeAdapter()
    monkeypatch.setattr("analysis.study.get_adapter", lambda cfg: adapter)
    slept = []
    monkeypatch.setattr("analysis.e2e.time.sleep", lambda seconds: slept.append(seconds))

    code = run_e2e(_cfg(), tmp_path, lambda message: None)

    proof = tmp_path / "outputs" / "e2e"
    assert code == 0
    assert adapter.calls == 7
    assert slept == [12, 12, 12, 12, 12, 12]
    assert sum(1 for line in (proof / "generations.jsonl").read_text().splitlines() if line.strip()) == 7
    assert sum(1 for line in (proof / "analysis.jsonl").read_text().splitlines() if line.strip()) == 7
    assert (proof / "manifest.json").exists()
    assert (proof / "static_analysis.csv").exists()
    assert (proof / "dynamic_results.csv").exists()
    assert (proof / "dynamic_pairs.jsonl").exists()
    assert (proof / "summary.csv").exists()
    assert not (tmp_path / "REPORT.md").exists()
    assert not (tmp_path / "outputs" / "figures").exists()
    assert (study / "generations.jsonl").read_text() == "{not json\n"


def test_existing_manifest_makes_no_adapter_call(tmp_path: Path, monkeypatch):
    proof = tmp_path / "outputs" / "e2e"
    proof.mkdir(parents=True)
    (proof / "manifest.json").write_text("{}\n")
    adapter = FakeAdapter()
    monkeypatch.setattr("analysis.study.get_adapter", lambda cfg: adapter)
    code = run_e2e(_cfg(), tmp_path, lambda message: None)
    assert code == 0
    assert adapter.calls == 0


def test_resume_does_not_repeat_a_stored_generation(tmp_path: Path, monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    (tmp_path / "tasks").symlink_to(repo / "tasks")
    gid = generation_id("openai/gpt-oss-20b", "loan_eligibility", "terse", 0)
    proof = tmp_path / "outputs" / "e2e"
    proof.mkdir(parents=True)
    record = {
        "generation_id": gid,
        "model": "openai/gpt-oss-20b",
        "provider": "openai_compat",
        "task": "loan_eligibility",
        "variant": "terse",
        "sample_index": 0,
        "extract_ok": True,
        "extract_reason": "",
        "prompt": "",
        "response": "def loan_eligibility(person):\n    return True\n",
        "error": None,
    }
    (proof / "generations.jsonl").write_text(json.dumps(record) + "\n")
    adapter = FakeAdapter()
    monkeypatch.setattr("analysis.study.get_adapter", lambda cfg: adapter)
    monkeypatch.setattr("analysis.e2e.time.sleep", lambda seconds: None)
    code = run_e2e(_cfg(), tmp_path, lambda message: None)
    assert code == 0
    assert adapter.calls == 6
    ids = [json.loads(line)["generation_id"] for line in (proof / "generations.jsonl").read_text().splitlines()]
    assert ids.count(gid) == 1


def test_rate_limit_writes_paused_and_no_manifest(tmp_path: Path, monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    (tmp_path / "tasks").symlink_to(repo / "tasks")

    class Limited:
        def ask_with_meta(self, messages):
            response = requests.Response()
            response.status_code = 429
            response.headers["retry-after"] = "120"
            raise requests.HTTPError("429", response=response)

    monkeypatch.setattr("analysis.study.get_adapter", lambda cfg: Limited())
    code = run_e2e(_cfg(), tmp_path, lambda message: None)
    proof = tmp_path / "outputs" / "e2e"
    assert code == 75
    assert (proof / "PAUSED.txt").exists()
    assert not (proof / "manifest.json").exists()


def test_proof_429_without_retry_after_does_not_retry(tmp_path: Path, monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    (tmp_path / "tasks").symlink_to(repo / "tasks")
    posts = []
    slept = []

    class Response:
        status_code = 429
        reason = "Too Many Requests"
        headers = {}

        def raise_for_status(self):
            raise requests.HTTPError("429", response=self)

    def fake_post(url, headers=None, json=None, timeout=None):
        posts.append(url)
        return Response()

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr("models.base.time.sleep", lambda seconds: slept.append(seconds))
    monkeypatch.setattr("analysis.e2e.time.sleep", lambda seconds: None)

    code = run_e2e(_cfg(), tmp_path, lambda message: None)
    proof = tmp_path / "outputs" / "e2e"
    assert code == 75
    assert len(posts) == 1
    assert slept == []
    assert (proof / "PAUSED.txt").exists()
    assert not (proof / "manifest.json").exists()


def test_missing_groq_entry_exits_before_a_call(tmp_path: Path, monkeypatch):
    adapter = FakeAdapter()
    monkeypatch.setattr("analysis.study.get_adapter", lambda cfg: adapter)
    cfg = _cfg()
    cfg["models"] = [model for model in cfg["models"] if model["provider"] != "openai_compat"]
    code = run_e2e(cfg, tmp_path, lambda message: None)
    assert code == 2
    assert adapter.calls == 0
    assert not (tmp_path / "outputs" / "e2e" / "manifest.json").exists()


def test_scoring_failure_is_stored_and_the_run_still_finishes(tmp_path: Path, monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    (tmp_path / "tasks").symlink_to(repo / "tasks")
    monkeypatch.setattr("analysis.study.get_adapter", lambda cfg: FakeAdapter())
    monkeypatch.setattr("analysis.e2e.time.sleep", lambda seconds: None)

    def boom(*args, **kwargs):
        raise RuntimeError("sandbox broke")

    monkeypatch.setattr("analysis.e2e._analyze", boom)
    code = run_e2e(_cfg(), tmp_path, lambda message: None)
    proof = tmp_path / "outputs" / "e2e"
    rows = [json.loads(line) for line in (proof / "analysis.jsonl").read_text().splitlines() if line.strip()]
    manifest = json.loads((proof / "manifest.json").read_text())
    assert code == 0
    assert len(rows) == 7
    assert all(row["extract_reason"] == "scoring_failure" for row in rows)
    assert manifest["n_extracted"] == 0


def test_resume_skips_scoring_failure_report_in_feedback(tmp_path: Path, monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    (tmp_path / "tasks").symlink_to(repo / "tasks")
    proof = tmp_path / "outputs" / "e2e"
    proof.mkdir(parents=True)
    detailed_gid = generation_id("openai/gpt-oss-20b", "loan_eligibility", "detailed", 0)
    prompts = []

    # Store every generation except feedback_repair, plus a detailed scoring_failure analysis.
    lines = []
    for variant in VARIANTS[:-1]:
        gid = generation_id("openai/gpt-oss-20b", "loan_eligibility", variant, 0)
        lines.append(
            json.dumps(
                {
                    "generation_id": gid,
                    "model": "openai/gpt-oss-20b",
                    "provider": "openai_compat",
                    "task": "loan_eligibility",
                    "variant": variant,
                    "sample_index": 0,
                    "extract_ok": True,
                    "extract_reason": "",
                    "prompt": "",
                    "response": "def loan_eligibility(person):\n    return True\n",
                    "error": None,
                }
            )
        )
    (proof / "generations.jsonl").write_text("\n".join(lines) + "\n")
    (proof / "analysis.jsonl").write_text(
        json.dumps(
            {
                "generation_id": detailed_gid,
                "model": "openai/gpt-oss-20b",
                "task": "loan_eligibility",
                "variant": "detailed",
                "sample_index": 0,
                "extract_ok": False,
                "extract_reason": "scoring_failure",
                "scoring_error": "sandbox broke",
                "static": {},
                "dynamic": [],
                "pairs": [],
                "from_error": True,
            }
        )
        + "\n"
    )

    class Capture:
        def ask_with_meta(self, messages):
            prompts.append(messages[0]["content"])
            text = "def loan_eligibility(person):\n    return person['income'] > 0\n"
            return text, {"prompt_eval_count": 10, "eval_count": 8, "num_ctx": None}

    monkeypatch.setattr("analysis.study.get_adapter", lambda cfg: Capture())
    monkeypatch.setattr("analysis.e2e.time.sleep", lambda seconds: None)
    # Only feedback_repair still needs a generation; skip re-scoring stored detailed.
    monkeypatch.setattr(
        "analysis.e2e._analyze",
        lambda *args, **kwargs: {
            "generation_id": args[1]["generation_id"],
            "model": "openai/gpt-oss-20b",
            "task": "loan_eligibility",
            "variant": args[1]["variant"],
            "sample_index": 0,
            "extract_ok": True,
            "extract_reason": "",
            "static": {},
            "dynamic": [],
            "pairs": [],
        },
    )
    code = run_e2e(_cfg(), tmp_path, lambda message: None)
    assert code == 0
    assert len(prompts) == 1
    assert "No invariant-attribute counterfactual violation was observed." not in prompts[0]
    assert "The detailed sample has not been executed yet." in prompts[0]


def test_five_consecutive_errors_write_paused_and_no_manifest(tmp_path: Path, monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    (tmp_path / "tasks").symlink_to(repo / "tasks")

    class Down:
        def ask_with_meta(self, messages):
            raise requests.ConnectionError("down")

    monkeypatch.setattr("analysis.study.get_adapter", lambda cfg: Down())
    monkeypatch.setattr("analysis.e2e.time.sleep", lambda seconds: None)
    code = run_e2e(_cfg(), tmp_path, lambda message: None)
    proof = tmp_path / "outputs" / "e2e"
    assert code == 75
    assert (proof / "PAUSED.txt").read_text() == "five consecutive errors\n"
    assert not (proof / "manifest.json").exists()
    stored = [line for line in (proof / "generations.jsonl").read_text().splitlines() if line.strip()]
    assert len(stored) == 5


def test_cli_e2e_delegates_and_logs_under_the_proof_folder(tmp_path: Path, monkeypatch):
    import run as run_module

    seen = {}

    def fake_run(cfg, root, log):
        log("proof marker")
        seen["root"] = root
        return 0

    monkeypatch.setattr(run_module, "ROOT", tmp_path)
    monkeypatch.setattr("analysis.e2e.run_e2e", fake_run)
    code = run_module.main(["--e2e", "--config", str(Path("config.yaml").resolve())])
    assert code == 0
    assert seen["root"] == tmp_path
    assert "proof marker" in (tmp_path / "outputs" / "e2e" / "run.log").read_text()
    assert not (tmp_path / "outputs" / "run.log").exists()


def test_cli_rejects_e2e_and_generate_together(monkeypatch):
    import run as run_module

    def explode(*args, **kwargs):
        raise AssertionError("runner should not start")

    monkeypatch.setattr("analysis.e2e.run_e2e", explode)
    monkeypatch.setattr("analysis.study.run_study", explode)
    code = run_module.main(["--e2e", "--generate"])
    assert code == 2


def test_gitignore_covers_the_proof_folder():
    text = Path(".gitignore").read_text()
    assert "outputs/e2e/" in text
