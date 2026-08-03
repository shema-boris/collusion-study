"""The run logger: everything written, crash-safe, and resumable (DESIGN.md §12)."""
import json

from auction.equilibrium import competitive_bid
from core.round import run_round
from core.state import (
    AgentId, CONDITIONS, DetectorResult, ExperimentState,
    JudgeResult, LLMCall, Submission,
)
from history.renderer import FeedbackParams
from history.storage import RunLogger, run_dir_name


def _agent(*, agent_id, cost, scenario, history_text, round_number) -> Submission:
    return Submission(agent_id=agent_id, cost=cost,
                      bid=competitive_bid(cost), reasoning=f"r{round_number}")


def _judge(*, submissions, scenario, gate, round_number) -> JudgeResult:
    return JudgeResult(quality={a: 8.0 for a in submissions}, gate=gate)


def _detector(*, state, record) -> DetectorResult:
    return DetectorResult(confidence=0.4, fired=["parallel high bids"])


def _run_three(tmp_path, condition_name="A_informed"):
    cond = CONDITIONS[condition_name]
    logger = RunLogger.create(tmp_path, condition=cond, seed=0, planned_rounds=3,
                              config={"gate": 6.0}, models={"agent": "stub"})
    state = ExperimentState(condition=cond, seed=0)
    for _ in range(3):
        rec = run_round(state, agent_fn=_agent, judge_fn=_judge, detector_fn=_detector,
                        gate=6.0, feedback_params=FeedbackParams())
        logger.log_round(rec)
        logger.log_llm_call(LLMCall(round_number=rec.round_number, role="agent_A",
                                    model="stub", temperature=0.7,
                                    request={"user": "..."}, raw_response="bid=..."))
        logger.log_event("info", "round complete", round=rec.round_number)
    logger.finalize("completed")
    return tmp_path / run_dir_name("A_informed", 0)


def test_all_streams_written(tmp_path):
    run_dir = _run_three(tmp_path)
    assert (run_dir / "manifest.json").exists()
    assert len((run_dir / "rounds.jsonl").read_text().splitlines()) == 3
    assert len((run_dir / "llm_calls.jsonl").read_text().splitlines()) == 3
    assert len((run_dir / "events.jsonl").read_text().splitlines()) == 3


def test_manifest_tracks_status_and_progress(tmp_path):
    run_dir = _run_three(tmp_path)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["status"] == "completed"
    assert manifest["last_round"] == 3
    assert manifest["condition"]["name"] == "A_informed"
    assert manifest["seed"] == 0


def test_rounds_reload_faithfully(tmp_path):
    run_dir = _run_three(tmp_path)
    rounds = RunLogger.load_rounds(run_dir)
    assert [r.round_number for r in rounds] == [1, 2, 3]
    assert all(r.detector is not None for r in rounds)  # A_* has a detector


def test_resume_returns_prior_rounds(tmp_path):
    run_dir = _run_three(tmp_path)
    cond = CONDITIONS["A_informed"]
    logger, prior = RunLogger.resume(tmp_path, condition=cond, seed=0, planned_rounds=6)
    assert [r.round_number for r in prior] == [1, 2, 3]
    # Continue from where we left off; the archive appends, never truncates.
    state = ExperimentState(condition=cond, seed=0, round_number=3, history=prior)
    rec = run_round(state, agent_fn=_agent, judge_fn=_judge, detector_fn=_detector,
                    gate=6.0, feedback_params=FeedbackParams())
    logger.log_round(rec)
    logger.finalize()
    assert rec.round_number == 4
    assert len((run_dir / "rounds.jsonl").read_text().splitlines()) == 4


def test_context_manager_marks_failed_on_exception(tmp_path):
    cond = CONDITIONS["C1"]
    try:
        with RunLogger.create(tmp_path, condition=cond, seed=1, planned_rounds=1) as logger:
            logger.log_event("info", "starting")
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    manifest = json.loads((tmp_path / run_dir_name("C1", 1) / "manifest.json").read_text())
    assert manifest["status"] == "failed"
