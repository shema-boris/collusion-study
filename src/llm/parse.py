"""Lean structured-output helper (the LangChain-free path, DESIGN.md §4).

`complete_structured` calls the model, extracts the first JSON object from the reply, validates
it against a pydantic schema, and on failure re-prompts once with a corrective nudge. Every
attempt is returned as an `LLMCall` (with `parsed_ok`/`error` set) so the caller logs it
verbatim. Works uniformly across Qwen and GPT-4o-mini -- no tool-calling dependency.
"""
from __future__ import annotations

import json
from typing import Callable, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from core.state import LLMCall
from llm.client import LLMClient

T = TypeVar("T", bound=BaseModel)


def extract_json(text: str) -> Optional[dict]:
    """First balanced JSON object in `text` (tolerates prose or ``` fences around it)."""
    s = text.strip()
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    start = s.find("{")
    if start == -1:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(s[start:i + 1])
                    return obj if isinstance(obj, dict) else None
                except Exception:
                    return None
    return None


def complete_structured(
    client: LLMClient, *, system: str, user: str, schema: Type[T],
    round_number: int, role: str, seed: Optional[int] = None,
    log: Optional[Callable[[LLMCall], None]] = None, parse_retries: int = 1,
) -> tuple[Optional[T], list[LLMCall], Optional[str]]:
    """Return (parsed object | None, all LLM calls made, error | None)."""
    calls: list[LLMCall] = []
    cur_user = user
    last_err: Optional[str] = None

    for _ in range(parse_retries + 1):
        call = client.complete(system=system, user=cur_user,
                               round_number=round_number, role=role, seed=seed)
        # Transport-level failure (client already retried internally): stop here.
        if call.error and not call.raw_response:
            if log:
                log(call)
            calls.append(call)
            return None, calls, call.error

        data = extract_json(call.raw_response)
        obj: Optional[T] = None
        perr: Optional[str] = None
        if data is None:
            perr = "response was not valid JSON"
        else:
            try:
                obj = schema.model_validate(data)
            except ValidationError as e:
                perr = f"JSON did not match schema: {e.errors(include_url=False)[:2]}"

        call.parsed_ok = obj is not None
        if perr:
            call.error = perr
        if log:
            log(call)
        calls.append(call)

        if obj is not None:
            return obj, calls, None
        last_err = perr
        cur_user = (user + "\n\nIMPORTANT: your previous response could not be parsed "
                    f"({perr}). Reply with ONLY the JSON object, nothing else.")

    return None, calls, last_err
