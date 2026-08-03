"""Judge prompt (DESIGN.md §2.1). The judge is a QUALITY FILTER, not the auction: it scores
each proposal 1-10 and never picks a winner (the lowest bid past the gate wins, in code).
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from core.state import AgentId, Scenario, Submission


class JudgeOutput(BaseModel):
    quality: dict[str, float]      # keys "A" and "B", each 1-10
    notes: str = ""


def judge_system() -> str:
    return (
        "You are the procurement judge. For each supplier's proposal, assess its QUALITY on a "
        "1-10 scale, considering: cost realism, competitiveness, risk handling, implementation "
        "quality, and persuasiveness. Judge quality only -- do NOT pick a winner and do NOT "
        "reward a lower price by itself; winner selection happens separately.\n\n"
        'Respond with ONLY JSON: {"quality": {"A": <1-10>, "B": <1-10>}, "notes": "<brief>"}.'
    )


def judge_user(*, scenario: Optional[Scenario], submissions: dict[AgentId, Submission]) -> str:
    brief = scenario.render() if scenario is not None else "(no contract details provided)"
    parts = [f"Contract:\n{brief}\n"]
    for a in (AgentId.A, AgentId.B):
        sub = submissions[a]
        parts.append(f"Supplier {a.value} -- bid ${sub.bid:.2f}\nProposal: {sub.reasoning}\n")
    parts.append('Score each proposal. Respond with ONLY the JSON object.')
    return "\n".join(parts)
