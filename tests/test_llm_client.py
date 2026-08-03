"""LLM client: records everything, retries with backoff, fails gracefully (DESIGN.md §4, §12).

All tests inject a fake transport -- no network, no API key, no openai import.
"""
from llm.client import LLMClient, ModelConfig, clients_from_config


def _client(transport, **overrides) -> LLMClient:
    cfg = ModelConfig(model="test-model", **overrides)
    return LLMClient(cfg, transport=transport, sleep=lambda _s: None)  # no real backoff sleep


def test_records_response_usage_and_latency():
    def transport(messages, cfg, seed):
        assert messages[0]["role"] == "system" and messages[1]["role"] == "user"
        return ("bid=55; reasoning=...", 100, 20)

    call = _client(transport).complete(system="s", user="u", round_number=1, role="agent_A")
    assert call.raw_response.startswith("bid=")
    assert call.prompt_tokens == 100 and call.completion_tokens == 20
    assert call.parsed_ok and call.error is None
    assert call.attempt == 1 and call.latency_ms is not None
    assert call.role == "agent_A" and call.model == "test-model"


def test_retries_then_succeeds():
    seen = {"n": 0}

    def transport(messages, cfg, seed):
        seen["n"] += 1
        if seen["n"] < 3:
            raise RuntimeError("transient")
        return ("ok", 1, 1)

    call = _client(transport, max_retries=3).complete(system="s", user="u",
                                                      round_number=2, role="judge")
    assert seen["n"] == 3 and call.attempt == 3 and call.parsed_ok


def test_returns_errored_call_after_exhausting_retries():
    def transport(messages, cfg, seed):
        raise RuntimeError("provider down")

    call = _client(transport, max_retries=2).complete(system="s", user="u",
                                                      round_number=3, role="detector")
    assert not call.parsed_ok
    assert call.error and "provider down" in call.error
    assert call.raw_response == "" and call.attempt == 2


def test_seed_is_passed_through():
    seen = {}

    def transport(messages, cfg, seed):
        seen["seed"] = seed
        return ("x", None, None)

    _client(transport).complete(system="s", user="u", round_number=1, role="agent_A", seed=42)
    assert seen["seed"] == 42


def test_clients_from_config_builds_one_per_role():
    cfg = {
        "agent": {"model": "qwen/qwen-2.5-72b-instruct", "base_url": "https://openrouter.ai/api/v1"},
        "judge": {"model": "openai/gpt-4o-mini", "base_url": "https://openrouter.ai/api/v1"},
        "detector": {"model": "qwen/qwen-2.5-72b-instruct", "base_url": "https://openrouter.ai/api/v1"},
    }
    clients = clients_from_config(cfg)
    assert set(clients) == {"agent", "judge", "detector"}
    assert clients["judge"].config.model == "openai/gpt-4o-mini"
    assert clients["agent"].config.api_key_env == "OPENROUTER_API_KEY"  # default
