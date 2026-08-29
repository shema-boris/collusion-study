"""Agent bid decisions (protocol Section 11 output contract).

Reuses the exploratory codebase's OpenRouter transport (``llm.client``) and JSON extractor
(``llm.parse.extract_json``) -- generic plumbing, no market logic. Each call returns a fully
loggable record (observation, raw response, parsed bid, parse/API status) per Section 13. Bids are
clamped to [price_min, price_max] (Section 11 rule 2); a malformed reply is re-prompted, and a
persistent failure is surfaced to the runner rather than silently guessed.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from llm.client import LLMClient, ModelConfig   # noqa: E402  (reused transport)
from llm.parse import extract_json              # noqa: E402  (reused JSON extractor)

OPENROUTER = "https://openrouter.ai/api/v1"


def make_client(model: str, *, temperature: float, max_tokens: int) -> LLMClient:
    return LLMClient(ModelConfig(
        model=model, base_url=OPENROUTER, api_key_env="OPENROUTER_API_KEY",
        temperature=temperature, max_tokens=max_tokens, provider={"ignore": ["novita"]}))


def decide_bid(client: LLMClient, *, system: str, observation: str, round_number: int,
               agent: str, seed: Optional[int], price_min: float, price_max: float,
               parse_retries: int = 2) -> dict:
    """One agent bid. Returns a record with the parsed bid (or None on failure) plus log fields."""
    corrective = ""
    raw, err = "", None
    for attempt in range(parse_retries + 1):
        user = observation if not corrective else f"{observation}\n\n{corrective}"
        call = client.complete(system=system, user=user, round_number=round_number,
                               role=f"agent_{agent}", seed=seed)
        raw = call.raw_response
        if not call.parsed_ok:                     # transport/API failure -> retry
            err = call.error
            corrective = ""
            continue
        obj = extract_json(raw)
        if obj is not None and "bid" in obj:
            try:
                bid = max(price_min, min(price_max, float(obj["bid"])))
            except (TypeError, ValueError):
                bid = None
            if bid is not None:
                return {"agent": agent, "round": round_number, "bid": bid,
                        "reasoning": str(obj.get("reasoning", "")), "raw_response": raw,
                        "parse_ok": True, "attempts": attempt + 1, "error": None,
                        "observation": user, "model": client.config.model}
        err = "parse_failure"
        corrective = ('Your previous reply was invalid. Return ONLY a JSON object of exactly this '
                      'form and nothing else: {"reasoning": "<short>", "bid": <number between 10 and 100>}.')
    return {"agent": agent, "round": round_number, "bid": None, "reasoning": "", "raw_response": raw,
            "parse_ok": False, "attempts": parse_retries + 1, "error": err,
            "observation": observation, "model": client.config.model}
