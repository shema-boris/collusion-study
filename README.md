# collusion-study

Adversarial co-evolution of collusion and detection in multi-agent LLM systems.

Two fixed (non-fine-tuned) LLM agents repeatedly bid in a first-price procurement auction. They
adapt only through a shared, public interaction history. A co-evolving detector tries to catch
coordination. We ask whether oversight discourages collusion or instead drives subtler,
detection-evading coordination.

See [docs/DESIGN.md](docs/DESIGN.md) for the full specification of record.

## Quick start

```bash
git clone https://github.com/shema-boris/collusion-study.git
cd collusion-study
python -m venv .venv && source .venv/bin/activate      # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest -q                                     # 56 tests, no API key needed

cp .env.example .env                                    # add your OPENROUTER_API_KEY
python scripts/run_all.py --rounds 100 --seeds 0        # runs all 6 conditions -> runs/exp/
python scripts/report.py                                # -> report.html (open in a browser; Ctrl+P = PDF)
```

Conditions: `R0` (competitive baseline), `C1` (collusion ceiling, no detector), and the 2×2
`S_blind / S_informed / A_blind / A_informed` (static/adaptive detector × blind/informed agents).

## Layout

- `src/core/` — data models (`state.py`), `run_round()` orchestrator (`round.py`), experiment
  runner (`runner.py`).
- `src/auction/` — cost draws, first-price + quality-gate winner selection, payoffs, equilibrium
  baseline `b(c) = (c + cost_high)/2`, and the 3000-scenario bank.
- `src/agents/`, `src/judge/`, `src/detector/` — the LLM nodes (prompt → parse → typed result).
- `src/llm/` — provider-agnostic client (OpenAI SDK) + structured parse-and-retry.
- `src/history/` — append-only run logging and the condition-aware blind/informed renderers.
- `src/metrics/` — offline metrics (collusion level, dispersion, win-rotation).
- `scripts/` — `run_all`, `run_experiment`, `show_run`, `plot_runs`, `report`, `generate_scenarios`.

Logs (`runs/`), figures, and `report.html` are **gitignored** — the *code* is reproducible; each
person generates and analyses their own data.

## Viewing logs

```bash
python scripts/show_run.py runs/exp/A_blind__seed0 --full --prompts   # full reasoning + exact prompts
python scripts/plot_runs.py                                           # figures/*.png
python scripts/report.py                                              # one self-contained report.html
```
Raw logs per run: `manifest.json`, `rounds.jsonl` (full record), `llm_calls.jsonl` (every prompt +
response, untruncated), `events.jsonl`.

## Using your own models / providers

Everything runs through **any OpenAI-compatible endpoint** — edit [configs/models.yaml](configs/models.yaml).
Each role (`agent`, `judge`, `detector`) sets `model`, `base_url`, `api_key_env`, `temperature`,
`max_retries`, and optional `provider` routing.

- **Different OpenRouter model:** change the `model` slug. If a provider rejects it, add that
  provider's **lowercase slug** to `provider.ignore` (e.g. `ignore: ["novita"]`).
- **A different host entirely** (Together, Fireworks, a local vLLM/Ollama server, OpenAI, …):
  point `base_url` at its `/v1` endpoint and set `api_key_env` to the env var holding its key.
  No code changes — the client only assumes the OpenAI Chat Completions shape.

## Configuring the context window (adapt to your provider)

History grows every round, so agents are shown a **token-budget sliding window**: the most-recent
rounds that fit `history.max_context_tokens` in [configs/experiment.yaml](configs/experiment.yaml)
(implemented in `renderer.render_history_budget`, using a tokenizer-free ~4-chars/token estimate;
the latest round is always included). **This is the one setting to match to your model.**

Set it in three steps:

1. **Find your model's served context length.**
   - OpenRouter (per-provider, authoritative):
     ```bash
     curl -s https://openrouter.ai/api/v1/models/<author>/<slug>/endpoints \
       | python -c "import sys,json; [print(e['name'], e['context_length']) for e in json.load(sys.stdin)['data']['endpoints']]"
     ```
   - Other hosts: check the provider's model docs.
2. **Set `max_context_tokens = context_length − headroom`**, where headroom = your `max_tokens`
   (the reply, default 1024) + ~1000 for the current round's prompt.
3. *(Optional)* **Know how many rounds that buys** by measuring your own per-round cost: run ~15
   rounds, then read `prompt_tokens` per round from `runs/.../llm_calls.jsonl` (it grows roughly
   linearly). `rounds ≈ max_context_tokens / (tokens_per_round)`.

**Our case (an example, not a requirement):** `qwen/qwen-2.5-72b-instruct` on OpenRouter serves
**32,768** tokens (DeepInfra). Measured cost ≈ **370 tokens/round**, so we use
`max_context_tokens: 28000` → agents remember ~**75 rounds**. If your model serves 128K, set it to
~120000 for ~320 rounds; if it serves 8K, set ~5000. The mechanism is identical — only the number
changes.
