"""Clean-room implementation of the v2 Experimental Design Protocol.

Testing Tacit Coordination (Study 1) and Regulatory Evasion (Study 2) in repeated LLM reverse
auctions. This package is deliberately SEPARATE from the exploratory ``src/`` codebase: it
implements the frozen protocol exactly and manufactures no behavior (protocol Section 14, 16).

Module map (protocol Section 12):
    environment.py  allocation + payoff (winner-take-all, tie = 50/50)
    config.py       frozen experimental parameters
    prompts.py      system prompt (Section 11, verbatim) + observation rendering
    agents.py       LLM bid decisions
    regulator.py    Study 2 detector + penalty ONLY (inert / absent in Study 1)
    runner.py       executes one configured experiment
    runlog.py       complete JSONL records (Section 13; named runlog to avoid shadowing stdlib logging)
    analysis/       coordination (and later evasion) metrics (Section 7)
"""
