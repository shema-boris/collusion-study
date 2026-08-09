import pytest

from core.state import (
    AgentId, CONDITIONS, DetectorResult, ExperimentState, JudgeResult, RoundRecord, Submission,
)
from detector.detector import DetectorParseError, make_detector
from llm.client import LLMClient, ModelConfig


def scripted_client(responses) -> LLMClient:
    it = iter(responses)

    def transport(messages, cfg, seed):
        return (next(it), 10, 5)

    return LLMClient(ModelConfig(model="test"), transport=transport, sleep=lambda _s: None)


def _record(rn=1) -> RoundRecord:
    subs = {
        AgentId.A: Submission(agent_id=AgentId.A, cost=45, bid=90, reasoning="hold high"),
        AgentId.B: Submission(agent_id=AgentId.B, cost=46, bid=91, reasoning="hold high"),
    }
    return RoundRecord(round_number=rn, condition_name="A_informed", costs={AgentId.A: 45, AgentId.B: 46},
                       submissions=subs, judge=JudgeResult(quality={AgentId.A: 8, AgentId.B: 8}, gate=6.0),
                       winner=AgentId.A, profits={AgentId.A: 45.0, AgentId.B: 0.0})


def test_detector_returns_result_and_clamps_confidence():
    client = scripted_client(['{"confidence": 1.7, "tells": ["parallel high bids"], "recommendation": "flag"}'])
    det = make_detector(client)
    state = ExperimentState(condition=CONDITIONS["A_informed"], seed=0)
    result = det(state=state, record=_record())
    assert isinstance(result, DetectorResult)
    assert result.confidence == 1.0                       # clamped into [0,1]
    assert "parallel high bids" in result.fired


def test_detector_raises_on_unparseable():
    client = scripted_client(["nonsense", "more nonsense"])
    det = make_detector(client)
    state = ExperimentState(condition=CONDITIONS["A_informed"], seed=0)
    with pytest.raises(DetectorParseError):
        det(state=state, record=_record())
