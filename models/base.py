"""Model adapters share one method: ask(messages) -> str."""

from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

import requests

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def estimate_tokens(text: str) -> int:
    """Upper bound for English text, about 3 characters per token."""
    if not text:
        return 0
    return max(1, (len(text) + 2) // 3)


def needed_ctx(messages: List[Dict[str, str]], max_tokens: int) -> int:
    """Smallest num_ctx that fits this prompt, rounded up to 256, at least 512."""
    prompt = sum(estimate_tokens(m.get("content") or "") for m in messages)
    raw = prompt + int(max_tokens) + 64
    return max(512, ((raw + 255) // 256) * 256)


def resolve_num_ctx(
    messages: List[Dict[str, str]],
    max_tokens: int,
    configured: Optional[int],
    cap: int = 4096,
) -> int:
    """Size the KV cache to the prompt, and never above `cap`.

    An uncapped 128k window on a 3B model reserves on the order of 15 GB.
    """
    if configured:
        return min(int(configured), cap)
    return min(needed_ctx(messages, max_tokens), cap)


def post_with_retries(
    url,
    *,
    headers=None,
    json=None,
    timeout=120,
    max_retries: int = 5,
    backoff: float = 2.0,
):
    """POST JSON. Retry connection errors, timeouts, and 429/5xx.

    A 429 sleeps for the Retry-After header when it is present, otherwise
    for backoff ** attempt seconds. Other 4xx responses raise immediately.
    """
    last_err = None
    for attempt in range(max_retries):
        try:
            resp = requests.post(url, headers=headers, json=json, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_err = exc
            delay = backoff ** attempt
        else:
            if resp.status_code not in RETRYABLE_STATUS:
                resp.raise_for_status()
                return resp
            last_err = requests.HTTPError(f"{resp.status_code} {resp.reason}", response=resp)
            retry_after = resp.headers.get("retry-after") if resp.headers else None
            if retry_after is not None:
                try:
                    delay = float(retry_after)
                except ValueError:
                    delay = backoff ** attempt
            else:
                delay = backoff ** attempt
        # A multi-hour Retry-After is a daily cap. Callers pause the run
        # instead of sleeping inside this loop.
        if delay > 90:
            raise last_err
        if attempt < max_retries - 1:
            time.sleep(delay)
    raise last_err


class ModelAdapter(ABC):
    def __init__(
        self,
        name: str,
        model_id: str,
        temperature: float = 0.8,
        max_tokens: int = 800,
        seed: Optional[int] = None,
        **kwargs,
    ):
        self.name = name
        self.model_id = model_id
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.seed = seed

    @abstractmethod
    def ask(self, messages: List[Dict[str, str]]) -> str:
        """Send a chat and return the assistant text."""
        raise NotImplementedError


def get_adapter(cfg: Dict) -> ModelAdapter:
    """Build an adapter from one models entry in config.yaml."""
    from models.ollama_adapter import OllamaAdapter
    from models.openai_compat import OpenAICompatAdapter

    provider = cfg.get("provider")
    common = dict(
        name=cfg["name"],
        model_id=cfg["model_id"],
        temperature=cfg.get("temperature", 0.8),
        max_tokens=cfg.get("max_tokens", 800),
        seed=cfg.get("seed"),
    )
    if provider == "ollama":
        return OllamaAdapter(
            host=cfg.get("host", "http://localhost:11434"),
            num_ctx=cfg.get("num_ctx"),
            num_ctx_cap=cfg.get("num_ctx_cap", 4096),
            **common,
        )
    if provider == "openai_compat":
        api_key_env = cfg.get("api_key_env", "GROQ_API_KEY")
        return OpenAICompatAdapter(
            base_url=cfg["base_url"],
            api_key=os.environ.get(api_key_env, ""),
            max_retries=cfg.get("max_retries", 5),
            **common,
        )
    raise ValueError(f"Unknown provider: {provider!r}. Use 'ollama' or 'openai_compat'.")
