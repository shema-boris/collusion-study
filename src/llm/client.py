"""Thin LLM client over the OpenAI SDK (DESIGN.md §4).

One abstraction serves every role because OpenRouter exposes an OpenAI-compatible `/v1` API:
agents + detector -> Qwen-72B, judge -> GPT-4o-mini, all through the same base_url and key,
differing only by model slug (configs/models.yaml).

The client is transport-injectable so it is fully testable without network or API keys. Each
call returns a populated ``LLMCall`` (raw response + usage + latency + attempt/error) ready to
log verbatim; parsing the raw text into a Submission/JudgeResult/DetectorResult is the node's
job (a separate concern, so parse-retries stay out of the transport layer).
"""
from __future__ import annotations

import os
import time
from typing import Callable, Optional

from pydantic import BaseModel

from core.state import LLMCall

# Transport contract: (messages, config, seed) -> (text, prompt_tokens, completion_tokens)
Transport = Callable[[list, "ModelConfig", Optional[int]], tuple]


class ModelConfig(BaseModel):
    model: str
    base_url: Optional[str] = None            # None => OpenAI default; set for OpenRouter
    api_key_env: str = "OPENROUTER_API_KEY"
    temperature: float = 0.7
    max_tokens: int = 1024
    timeout: float = 60.0
    max_retries: int = 3
    extra_headers: Optional[dict] = None       # e.g. OpenRouter ranking headers (optional)
    provider: Optional[dict] = None            # OpenRouter provider routing, e.g. {"ignore": ["Novita"]}


def _openai_transport(messages: list, cfg: "ModelConfig", seed: Optional[int]):
    from openai import OpenAI  # lazy import: not needed for tests / deterministic core

    client = OpenAI(base_url=cfg.base_url, api_key=os.environ.get(cfg.api_key_env),
                    timeout=cfg.timeout)
    kwargs = dict(model=cfg.model, messages=messages,
                  temperature=cfg.temperature, max_tokens=cfg.max_tokens)
    if seed is not None:
        kwargs["seed"] = seed                  # best-effort determinism where supported
    if cfg.extra_headers:
        kwargs["extra_headers"] = cfg.extra_headers
    if cfg.provider:
        kwargs["extra_body"] = {"provider": cfg.provider}   # OpenRouter routing preferences
    resp = client.chat.completions.create(**kwargs)
    # Some providers return a 200 with an error body and no choices; surface it so retry re-routes.
    choices = getattr(resp, "choices", None)
    if not choices:
        raise RuntimeError(f"provider returned no choices: {getattr(resp, 'error', None) or resp}")
    text = choices[0].message.content or ""
    usage = getattr(resp, "usage", None)
    pt = getattr(usage, "prompt_tokens", None) if usage else None
    ct = getattr(usage, "completion_tokens", None) if usage else None
    return text, pt, ct


class LLMClient:
    def __init__(self, config: ModelConfig, transport: Optional[Transport] = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.config = config
        self._transport = transport or _openai_transport
        self._sleep = sleep

    def complete(self, *, system: str, user: str, round_number: int, role: str,
                 seed: Optional[int] = None) -> LLMCall:
        """One completion with retry/backoff. Returns a populated LLMCall (errored on failure)."""
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
        request = {"system": system, "user": user}
        last_err: Optional[str] = None
        for attempt in range(1, self.config.max_retries + 1):
            t0 = time.perf_counter()
            try:
                text, pt, ct = self._transport(messages, self.config, seed)
                return LLMCall(
                    round_number=round_number, role=role, model=self.config.model,
                    temperature=self.config.temperature, request=request, raw_response=text,
                    prompt_tokens=pt, completion_tokens=ct,
                    latency_ms=(time.perf_counter() - t0) * 1000.0,
                    attempt=attempt, parsed_ok=True)
            except Exception as e:  # noqa: BLE001 - any transport error is retryable here
                last_err = str(e)
                if attempt < self.config.max_retries:
                    self._sleep(min(0.5 * (2 ** (attempt - 1)), 20.0))
        # Retries exhausted: return an errored call so a long run logs the failure and continues.
        return LLMCall(round_number=round_number, role=role, model=self.config.model,
                       temperature=self.config.temperature, request=request, raw_response="",
                       parsed_ok=False, error=last_err, attempt=self.config.max_retries)


def clients_from_config(models_cfg: dict) -> dict[str, LLMClient]:
    """Build one client per role from configs/models.yaml (roles: agent, judge, detector)."""
    return {role: LLMClient(ModelConfig(**cfg)) for role, cfg in models_cfg.items()}
