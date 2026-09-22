"""Offline tests for config loading, retries, and the adapter interface."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import requests

from models.base import ModelAdapter, get_adapter, post_with_retries, resolve_num_ctx
from run import load_config


ROOT = Path(__file__).resolve().parents[1]


class FakeAdapter(ModelAdapter):
    def ask(self, messages):
        return "canned-reply"


def test_fake_adapter_returns_canned_string():
    adapter = FakeAdapter(name="fake", model_id="fake-1", temperature=0.8, max_tokens=32)
    assert adapter.ask([{"role": "user", "content": "hi"}]) == "canned-reply"


def test_config_loads_seed_temperature_and_three_models():
    cfg = load_config(ROOT / "config.yaml")
    assert cfg["seed"] == 42
    assert cfg["temperature"] == 0.8
    assert cfg["n_samples"] == 5
    assert cfg["num_ctx_cap"] == 4096
    assert cfg["sandbox"]["per_call_timeout_s"] == 2
    ids = [m["model_id"] for m in cfg["models"]]
    assert ids == ["qwen2.5-coder:7b", "llama3.2:3b", "openai/gpt-oss-20b"]


def test_unknown_provider_is_rejected():
    with pytest.raises(ValueError):
        get_adapter({"provider": "nope", "name": "x", "model_id": "x"})


def test_retry_honors_retry_after_then_succeeds(monkeypatch):
    calls = {"n": 0}
    slept = []

    class Response:
        def __init__(self, status, body=None, retry_after=None):
            self.status_code = status
            self.reason = "nope" if status != 200 else "ok"
            self.headers = {}
            if retry_after is not None:
                self.headers["retry-after"] = str(retry_after)
            self._body = body or {"choices": [{"message": {"content": "ok"}}]}

        def json(self):
            return self._body

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(f"{self.status_code}", response=self)

    def fake_post(url, headers=None, json=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return Response(429, retry_after=0)
        return Response(200)

    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr("models.base.time.sleep", lambda s: slept.append(s))

    resp = post_with_retries("http://example.test", json={"a": 1}, max_retries=3, backoff=2.0)
    assert resp.status_code == 200
    assert calls["n"] == 2
    assert slept == [0]


def test_long_retry_after_raises_instead_of_sleeping(monkeypatch):
    slept = []

    class Response:
        status_code = 429
        reason = "slow down"
        headers = {"retry-after": "3600"}

        def raise_for_status(self):
            raise requests.HTTPError("429", response=self)

    monkeypatch.setattr(requests, "post", lambda *a, **k: Response())
    monkeypatch.setattr("models.base.time.sleep", lambda s: slept.append(s))
    with pytest.raises(requests.HTTPError):
        post_with_retries("http://example.test", max_retries=4, backoff=2.0)
    assert slept == []


def test_non_retryable_http_error_is_not_retried(monkeypatch):
    calls = {"n": 0}

    class Response:
        status_code = 401
        reason = "unauthorized"
        headers = {}

        def raise_for_status(self):
            raise requests.HTTPError("401", response=self)

        def json(self):
            return {}

    monkeypatch.setattr(requests, "post", lambda *a, **k: calls.__setitem__("n", calls["n"] + 1) or Response())
    with pytest.raises(requests.HTTPError):
        post_with_retries("http://example.test", max_retries=4)
    assert calls["n"] == 1


def test_num_ctx_is_capped_at_4096():
    messages = [{"role": "user", "content": "x" * 50000}]
    ctx = resolve_num_ctx(messages, max_tokens=800, configured=None, cap=4096)
    assert ctx == 4096


def test_num_ctx_shrinks_to_the_prompt_when_the_prompt_is_short():
    messages = [{"role": "user", "content": "write a function"}]
    ctx = resolve_num_ctx(messages, max_tokens=800, configured=None, cap=4096)
    assert 512 <= ctx < 4096


def test_openai_compat_payload_omits_unsupported_fields(monkeypatch):
    captured = {}

    class Response:
        status_code = 200
        reason = "ok"
        headers = {}

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "def f(person): return True"}}]}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return Response()

    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    adapter = get_adapter(
        {
            "provider": "openai_compat",
            "name": "GPT-OSS 20B",
            "model_id": "openai/gpt-oss-20b",
            "base_url": "https://api.groq.com/openai/v1",
            "api_key_env": "GROQ_API_KEY",
            "temperature": 0.8,
            "max_tokens": 800,
        }
    )
    text = adapter.ask([{"role": "user", "content": "hi"}])
    assert text.startswith("def f")
    assert captured["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    body = captured["json"]
    assert body["temperature"] == 0.8
    assert body["max_tokens"] == 800
    assert "logprobs" not in body
    assert "logit_bias" not in body
    assert os.environ["GROQ_API_KEY"] == "test-key"
