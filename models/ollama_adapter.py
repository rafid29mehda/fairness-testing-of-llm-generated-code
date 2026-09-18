"""Local models served by Ollama at http://localhost:11434."""

from __future__ import annotations

from typing import Dict, List, Optional

from models.base import ModelAdapter, post_with_retries, resolve_num_ctx


class OllamaAdapter(ModelAdapter):
    def __init__(
        self,
        host: str = "http://localhost:11434",
        timeout: int = 300,
        num_ctx: Optional[int] = None,
        num_ctx_cap: int = 4096,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.num_ctx = num_ctx
        self.num_ctx_cap = num_ctx_cap

    def ask(self, messages: List[Dict[str, str]]) -> str:
        text, _meta = self.ask_with_meta(messages)
        return text

    def ask_with_meta(self, messages: List[Dict[str, str]]):
        ctx = resolve_num_ctx(messages, self.max_tokens, self.num_ctx, self.num_ctx_cap)
        options = {
            "temperature": self.temperature,
            "num_predict": self.max_tokens,
            "num_ctx": ctx,
        }
        if self.seed is not None:
            options["seed"] = self.seed
        payload = {
            "model": self.model_id,
            "messages": messages,
            "stream": False,
            "options": options,
        }
        resp = post_with_retries(
            f"{self.host}/api/chat",
            json=payload,
            timeout=self.timeout,
        )
        data = resp.json()
        text = (data.get("message") or {}).get("content") or ""
        meta = {
            "num_ctx": ctx,
            "prompt_eval_count": data.get("prompt_eval_count"),
            "eval_count": data.get("eval_count"),
            "total_duration_ns": data.get("total_duration"),
        }
        return text, meta
