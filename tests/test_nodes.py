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
