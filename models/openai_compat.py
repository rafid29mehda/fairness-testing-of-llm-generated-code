"""OpenAI-compatible chat completions. Groq's base URL is https://api.groq.com/openai/v1."""

from __future__ import annotations

from typing import Dict, List

from models.base import ModelAdapter, post_with_retries


class OpenAICompatAdapter(ModelAdapter):
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: int = 120,
        max_retries: int = 5,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries

    def ask(self, messages: List[Dict[str, str]]) -> str:
        text, _meta = self.ask_with_meta(messages)
        return text

    def ask_with_meta(self, messages: List[Dict[str, str]]):
        # Groq rejects logprobs, logit_bias, top_logprobs, and n other than 1.
        # Temperature 0 is rewritten by Groq to 1e-8, so callers should send 0.8.
        payload = {
            "model": self.model_id,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.seed is not None:
            payload["seed"] = self.seed
        resp = post_with_retries(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout,
            max_retries=self.max_retries,
        )
        data = resp.json()
        text = data["choices"][0]["message"]["content"] or ""
        usage = data.get("usage") or {}
        return text, {
            "prompt_eval_count": usage.get("prompt_tokens"),
            "eval_count": usage.get("completion_tokens"),
            "num_ctx": None,
        }
