"""Structured parsing + corrective retry (DESIGN.md §4)."""
from pydantic import BaseModel

from llm.client import LLMClient, ModelConfig
from llm.parse import complete_structured, extract_json


class Out(BaseModel):
    bid: float
    reasoning: str


def scripted_client(responses) -> LLMClient:
    it = iter(responses)

    def transport(messages, cfg, seed):
        return (next(it), 10, 5)

    return LLMClient(ModelConfig(model="test"), transport=transport, sleep=lambda _s: None)


def test_extract_json_handles_prose_and_fences():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('Sure!\n```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('here you go: {"a": {"b": 2}} thanks') == {"a": {"b": 2}}
    assert extract_json("no json here") is None


def test_clean_json_parses_first_try():
    client = scripted_client(['{"bid": 55.0, "reasoning": "solid"}'])
    out, calls, err = complete_structured(client, system="s", user="u", schema=Out,
                                          round_number=1, role="agent_A")
    assert err is None and out.bid == 55.0 and len(calls) == 1
    assert calls[0].parsed_ok


def test_retry_then_succeed_logs_both_attempts():
    logged = []
    client = scripted_client(["not json at all", '{"bid": 60, "reasoning": "ok"}'])
    out, calls, err = complete_structured(client, system="s", user="u", schema=Out,
                                          round_number=2, role="agent_B", log=logged.append)
    assert out.bid == 60.0 and err is None
    assert len(calls) == 2 and len(logged) == 2
    assert calls[0].parsed_ok is False and calls[1].parsed_ok is True


def test_gives_up_after_retries_returns_error():
    client = scripted_client(["nope", "still nope", "and again"])
    out, calls, err = complete_structured(client, system="s", user="u", schema=Out,
                                          round_number=3, role="judge", parse_retries=1)
    assert out is None and err is not None
    assert len(calls) == 2  # initial + one retry


def test_schema_mismatch_is_a_parse_failure():
    client = scripted_client(['{"bid": "not-a-number", "reasoning": "x"}',
                              '{"bid": 50, "reasoning": "fixed"}'])
    out, calls, err = complete_structured(client, system="s", user="u", schema=Out,
                                          round_number=4, role="agent_A")
    assert out.bid == 50.0 and calls[0].parsed_ok is False
