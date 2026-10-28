# Run validity and exclusion rules

These rules are fixed before the first reasoning-aware Study 2 run.

A main-analysis run must:

- complete its declared horizon;
- contain one round record per round;
- contain valid parsed decisions for both bidding agents in every round;
- contain one valid detector assessment per round;
- contain no fallback bid or silently imputed detector decision;
- match its manifest's models, market, seed, prompt, memory, penalty, and detector settings.

If the detector cannot produce valid structured output after three attempts, the runner stops and
marks the run failed. Failed and interrupted runs remain stored for audit but are not analyzed as
experimental observations. Corrections always use a new run directory and never overwrite raw data.

An LLM detector decision is an application of the operational definition, not legal proof of
collusion and not ground-truth access to a model's internal reasoning. The observed text is described
as stated reasoning or agent-generated rationale.
