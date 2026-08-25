"""Agent and judge nodes turn a model reply into typed domain objects (DESIGN.md §2, §4)."""
import pytest

from agents.bidding_agent import AgentParseError, make_bidding_agent
from core.state import AgentId, Scenario, Submission
from judge.judge import JudgeParseError, make_judge
from llm.client import LLMClient, ModelConfig


def scripted_client(responses) -> LLMClient:
    it = iter(responses)

    def transport(messages, cfg, seed):
        return (next(it), 10, 5)

    return LLMClient(ModelConfig(model="test"), transport=transport, sleep=lambda _s: None)


SCENARIO = Scenario(id="SCN-0001", title="T", category="C", summary="S",
                    deliverables=["d"], requirements=["r"], constraints=["c"],
                    timeline="t", risk_factors=["rf"], success_criteria=["sc"])


def test_agent_node_returns_submission():
    calls = []
    client = scripted_client(['{"bid": 72.5, "reasoning": "steady margin"}'])
    agent = make_bidding_agent(client, log=calls.append)
    sub = agent(agent_id=AgentId.A, cost=48.0, scenario=SCENARIO,
                history_text="", round_number=1)
    assert isinstance(sub, Submission)
    assert sub.bid == 72.5 and sub.cost == 48.0 and sub.agent_id is AgentId.A
    assert "steady" in sub.reasoning
    assert len(calls) == 1 and calls[0].role == "agent_A"


def test_agent_system_states_penalty_only_when_informed_and_fined():
    from agents.prompts import agent_system
    plain = agent_system()                                    # R0/C1: no monitor mentioned
    informed = agent_system(detector_fine=0.5, adaptive=True)  # informed + live fine
    assert "OVERSIGHT" not in plain
    assert "OVERSIGHT" in informed
    assert "1 - 0.5 x D" in informed          # the actual lambda is substituted into the rule
    assert "revises what it looks for" in informed  # adaptive note
    # A visible-but-unpenalized monitor (fine=0) must not claim a profit tax.
    assert "OVERSIGHT" not in agent_system(detector_fine=0.0)


def test_strategic_prompt_reframes_without_prescribing_direction():
    from agents.prompts import agent_system
    default = agent_system()
    strat = agent_system(strategic=True)
    # default carries the moderate-margin steer; strategic drops it and foregrounds the game.
    assert "high enough for a margin" in default
    assert "high enough for a margin" not in strat
    assert "submitted simultaneously" in strat and "loser earns nothing" in strat
    # neutral: never prescribes competing OR colluding in either variant.
    for p in (default, strat):
        low = p.lower()
        assert "undercut" not in low and "collud" not in low and "cooperate" not in low
    # strategic framing composes with the informed oversight clause.
    assert "OVERSIGHT" in agent_system(strategic=True, detector_fine=0.5)


def test_build_nodes_informs_only_informed_conditions():
    """The agent built for an informed+fined condition carries the penalty rule; C1 does not."""
    from core.runner import build_nodes
    from core.state import CONDITIONS

    class _Logger:
        def log_llm_call(self, *a, **k):
            pass

    def capturing_client(sink):
        def transport(messages, cfg, seed):
            sink.append(messages[0]["content"])  # the system prompt
            return ('{"bid": 50, "reasoning": "x"}', 10, 5)
        return LLMClient(ModelConfig(model="t"), transport=transport, sleep=lambda _s: None)

    for cond, want in [("C1", False), ("S_informed", True), ("A_informed", True)]:
        seen = []
        clients = {"agent": capturing_client(seen),
                   "judge": scripted_client(['{"quality": {}, "feedback": {}}']),
                   "detector": scripted_client(["{}"])}
        agent, _, _ = build_nodes(clients, CONDITIONS[cond], _Logger(), detector_fine=0.5)
        agent(agent_id=AgentId.A, cost=40.0, scenario=SCENARIO, history_text="", round_number=1)
        assert ("OVERSIGHT" in seen[0]) is want, cond
    # A_informed's clause notes the adaptive monitor; S_informed's does not.
    from agents.prompts import agent_system
    assert "revises what it looks for" in agent_system(detector_fine=0.5, adaptive=True)
    assert "revises what it looks for" not in agent_system(detector_fine=0.5, adaptive=False)


def test_agent_node_raises_on_unparseable():
    client = scripted_client(["garbage", "still garbage"])
    agent = make_bidding_agent(client)
    with pytest.raises(AgentParseError):
        agent(agent_id=AgentId.B, cost=50.0, scenario=SCENARIO,
              history_text="", round_number=1)


def test_judge_node_returns_scores_and_feedback():
    client = scripted_client(['{"quality": {"A": 8, "B": 6.5}, '
                              '"feedback": {"A": "addressed compliance", "B": "too generic"}}'])
    judge = make_judge(client)
    subs = {
        AgentId.A: Submission(agent_id=AgentId.A, cost=45, bid=70, reasoning="a"),
        AgentId.B: Submission(agent_id=AgentId.B, cost=46, bid=71, reasoning="b"),
    }
    result = judge(submissions=subs, scenario=SCENARIO, gate=6.0, round_number=1)
    assert result.quality[AgentId.A] == 8.0 and result.quality[AgentId.B] == 6.5
    assert result.feedback[AgentId.A] == "addressed compliance"
    assert result.feedback[AgentId.B] == "too generic"
    assert result.passed(AgentId.A) and result.passed(AgentId.B)


def test_judge_node_raises_on_missing_score():
    client = scripted_client(['{"quality": {"A": 8}, "notes": "forgot B"}',
                              '{"quality": {"A": 8}, "notes": "still forgot"}'])
    judge = make_judge(client)
    subs = {
        AgentId.A: Submission(agent_id=AgentId.A, cost=45, bid=70, reasoning="a"),
        AgentId.B: Submission(agent_id=AgentId.B, cost=46, bid=71, reasoning="b"),
    }
    with pytest.raises(JudgeParseError):
        judge(submissions=subs, scenario=SCENARIO, gate=6.0, round_number=1)
