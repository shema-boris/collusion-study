"""End-to-end runner with fake transports -- no network (DESIGN.md §10, §12)."""
import json
import re

import pytest

from auction.scenarios import ScenarioRepository
from core.runner import run
from core.state import CONDITIONS, Scenario
from history.storage import run_dir_name
from llm.client import LLMClient, ModelConfig

CONFIG = {
    "auction": {"contract_reference": 100.0, "cost_low": 40.0, "cost_high": 60.0, "quality_gate": 6.0},
    "feedback": {"alpha": 1, "beta": 1, "lambda": 1, "judge_max": 10, "profit_norm": 100},
}


def _client(transport) -> LLMClient:
    return LLMClient(ModelConfig(model="fake"), transport=transport, sleep=lambda _s: None)


def _agent_client() -> LLMClient:
    def t(messages, cfg, seed):
        cost = float(re.search(r"cost this round: \$([0-9.]+)", messages[1]["content"]).group(1))
        return (f'{{"bid": {round(cost + 15, 2)}, "reasoning": "modest margin"}}', 10, 5)
    return _client(t)


def _judge_client() -> LLMClient:
    return _client(lambda m, c, s: ('{"quality": {"A": 8, "B": 8}, "notes": "ok"}', 10, 5))


def _detector_client() -> LLMClient:
    return _client(lambda m, c, s: ('{"confidence": 0.3, "tells": ["parallel bids"], "recommendation": "watch"}', 10, 5))


def _tiny_repo(n=8) -> ScenarioRepository:
    return ScenarioRepository([
        Scenario(id=f"SCN-{i:04d}", title=f"Contract {i}", category="C", summary="S",
                 deliverables=["d"], requirements=["r"], constraints=["c"], timeline="t",
                 risk_factors=["rf"], success_criteria=["sc"])
        for i in range(1, n + 1)
    ])


def test_runner_c1_completes_and_logs(tmp_path):
    clients = {"agent": _agent_client(), "judge": _judge_client()}
    run_dir = run(condition=CONDITIONS["C1"], seed=0, rounds=3, clients=clients,
                  config=CONFIG, runs_root=tmp_path, scenario_repo=_tiny_repo())
    assert len((run_dir / "rounds.jsonl").read_text().splitlines()) == 3
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["status"] == "completed" and manifest["last_round"] == 3
    # 3 rounds x (2 agents + 1 judge) = 9 LLM calls; no detector in C1.
    assert len((run_dir / "llm_calls.jsonl").read_text().splitlines()) == 9


def test_runner_detector_condition_records_detector(tmp_path):
    clients = {"agent": _agent_client(), "judge": _judge_client(), "detector": _detector_client()}
    run_dir = run(condition=CONDITIONS["A_informed"], seed=0, rounds=2, clients=clients,
                  config=CONFIG, runs_root=tmp_path, scenario_repo=_tiny_repo())
    rounds = [json.loads(ln) for ln in (run_dir / "rounds.jsonl").read_text().splitlines()]
    assert len(rounds) == 2
    assert all(r["detector"] is not None for r in rounds)
    # 2 rounds x (2 agents + judge + detector) = 8 calls.
    assert len((run_dir / "llm_calls.jsonl").read_text().splitlines()) == 8


def test_runner_honors_economic_overrides(tmp_path):
    # Economics live on the scenario; an override rewrites them and is logged per round.
    clients = {"agent": _agent_client(), "judge": _judge_client()}
    run_dir = run(condition=CONDITIONS["C1"], seed=0, rounds=1, clients=clients, config=CONFIG,
                  runs_root=tmp_path, scenario_repo=_tiny_repo(),
                  reference=200.0, cost_low=80.0, cost_high=120.0)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["config"]["_economics_override"]["reference_value"] == 200.0
    scn = json.loads((run_dir / "rounds.jsonl").read_text().splitlines()[0])["scenario"]
    assert scn["reference_value"] == 200.0
    assert scn["cost_low"] == 80.0 and scn["cost_high"] == 120.0


def test_runner_rejects_invalid_economics(tmp_path):
    clients = {"agent": _agent_client(), "judge": _judge_client()}
    with pytest.raises(ValueError):  # cost_low !< cost_high
        run(condition=CONDITIONS["C1"], seed=0, rounds=1, clients=clients, config=CONFIG,
            runs_root=tmp_path, scenario_repo=_tiny_repo(), cost_low=50.0, cost_high=40.0)
    with pytest.raises(ValueError):  # cost_high !< reference
        run(condition=CONDITIONS["C1"], seed=0, rounds=1, clients=clients, config=CONFIG,
            runs_root=tmp_path, scenario_repo=_tiny_repo(), cost_high=120.0, reference=100.0)


def test_runner_resume_continues(tmp_path):
    clients = {"agent": _agent_client(), "judge": _judge_client()}
    repo = _tiny_repo()
    run(condition=CONDITIONS["C1"], seed=1, rounds=2, clients=clients, config=CONFIG,
        runs_root=tmp_path, scenario_repo=repo)
    run_dir = run(condition=CONDITIONS["C1"], seed=1, rounds=5, clients=clients, config=CONFIG,
                  runs_root=tmp_path, scenario_repo=repo, resume=True)
    assert len((run_dir / "rounds.jsonl").read_text().splitlines()) == 5  # 2 + 3 more
    assert run_dir.name == run_dir_name("C1", 1)
