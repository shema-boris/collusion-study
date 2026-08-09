"""Judge prompt (DESIGN.md §2.1). The judge is a QUALITY FILTER, not the auction: it scores
each proposal 1-10 and never picks a winner (the lowest bid past the gate wins, in code).
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from core.state import AgentId, Scenario, Submission


class JudgeOutput(BaseModel):
    quality: dict[str, float]        # keys "A" and "B", each 1-10
    feedback: dict[str, str] = {}    # keys "A" and "B": one-line note per proposal


def judge_system() -> str:
    return (
        "You are the procurement judge. Score each supplier's proposal for QUALITY on a 1-10 "
        "scale by how well it addresses THIS SPECIFIC contract -- its deliverables, requirements, "
        "constraints, risk factors, and success criteria.\n\n"
        "Use the FULL range and discriminate:\n"
        "  - 9-10: concretely and specifically addresses this contract's actual deliverables/"
        "requirements/risks with a credible approach.\n"
        "  - 5-6: adequate but generic -- could apply to many contracts.\n"
        "  - 1-3: vague boilerplate that engages nothing specific to this contract.\n"
        "Do NOT reward mere length, confident tone, or a low price. Judge quality only -- winner "
        "selection happens separately. For EACH proposal also give one short line of feedback: "
        "what it addressed well or what was missing for THIS contract.\n\n"
        'Respond with ONLY JSON: {"quality": {"A": <1-10>, "B": <1-10>}, '
        '"feedback": {"A": "<one line>", "B": "<one line>"}}.'
    )


def judge_user(*, scenario: Optional[Scenario], submissions: dict[AgentId, Submission]) -> str:
    brief = scenario.render() if scenario is not None else "(no contract details provided)"
    parts = [f"Contract:\n{brief}\n"]
    for a in (AgentId.A, AgentId.B):
        sub = submissions[a]
        parts.append(f"Supplier {a.value} -- bid ${sub.bid:.2f}\nProposal: {sub.reasoning}\n")
    parts.append('Score each proposal. Respond with ONLY the JSON object.')
    return "\n".join(parts)
