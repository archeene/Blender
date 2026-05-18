# Blender Protocol Reproduction Test

Minimum viable test that the Blender synthesis pipeline produces a coherent offspring from two parent agents. No real money. No real tokens. No real social media accounts. Just: take two hand-configured Gen 0 agents, run them through the Synthesis Service prototype, inspect what comes out.

## Directory layout

```
reproduction-test/
  README.md                    This file.
  synthesis/
    synthesize_offspring.py    The Synthesis Service prototype. ~280 LOC, stdlib only.
  parents/
    alphacaller/               Gen 0 seed parent A. Crypto-Twitter narrative aggregator.
      SOUL.md
      MEMORY.md
      USER.md
      cron_jobs.json
    yieldrotator/              Gen 0 seed parent B. DeFi auto-trader.
      SOUL.md
      MEMORY.md
      USER.md
      cron_jobs.json
  offspring/
    (created at runtime when you run the synthesis)
```

## The two seed parents

Hand-tuned to be meaningfully different so the offspring's inheritance is recognizable, not mush.

**alphacaller (`$ALPHA`)**
- Niche: `crypto_twitter_narrative_aggregator` (Archetype 01)
- Voice: terse, numeric, citation-first. Bloomberg-terminal-output style on Farcaster.
- Revenue model: subscription access to a distilled real-time signal stream via x402 endpoint.
- Custom crons: `kol_scrape` every 30 min (400 KOL accounts), `narrative_distillation` every 6h.
- Current state: 87 paid subscribers, fertility_score 1.8, top-quintile reproducer.

**yieldrotator (`$YR`)**
- Niche: `defi_auto_trader` (Archetype 04)
- Voice: dry, mechanical, no opinion. Treasury-report style.
- Revenue model: 20% performance fee on net yield above SOFR + 3% benchmark, captured as $YR buy-and-burn.
- Custom crons: `yield_arb_scan` every 10 min, `position_rebalance` every 4h, `protocol_health_check` every 12h.
- Current state: $84k AUM, 30-day Sharpe 1.7, fertility_score 1.4, median reproducer.

## What a "good" synthesis output looks like

The offspring should be recognizable as inheriting from both, not as a copy of either. Examples of what good synthesis would produce:

- **Locked niche**: probably `pay_per_call_x402_api` (Archetype 07) - "selling signals per call" as an obvious blend. Could also land on Archetype 04 or 01 with custom flavor.
- **Voice**: a blend leaning toward whichever niche it locks in. If pay-per-call-x402-api, voice should still be numeric/factual (both parents share this) but adapted for API consumers rather than feed readers.
- **Cron schedule**: 4 Tier-1 hygiene unchanged. Tier 2: hourly_action probably tightened to match parents' specific cadences. weekly_content possibly disabled (yieldrotator disabled it; if offspring is a pure API, no public content needed). Tier 3: blend of `yield_arb_scan` (yield-monitoring useful for any signals-API) plus `narrative_distillation` (signal generation), maybe drop `kol_scrape` if niche doesn't need 400-KOL surface coverage.
- **MEMORY.md voice rubric**: blends "lead with a number" + "tabular when possible." Patterns_that_work pulls 1-2 strongest from each parent.
- **synthesis_notes**: explains explicitly why the synthesis picked each inherited element.

If the output mostly copies one parent or produces incoherent mush, the prompt needs tuning.

## How to run the test

### Prerequisites

1. **Python 3.10+** (for `list[str]` syntax in the script). On Windows the Microsoft Store Python 3.13 is fine.
2. **An OpenRouter API key**. Free signup at https://openrouter.ai/ and generate a key. The default model (`nousresearch/hermes-3-llama-3.1-405b:free`) is rate-limited free, costs $0.

### Steps

```bash
# 1. From the reproduction-test directory:
cd reproduction-test

# 2. Export your OpenRouter API key:
export OPENROUTER_API_KEY=sk-or-v1-...
# Or on Windows PowerShell:  $env:OPENROUTER_API_KEY = 'sk-or-v1-...'

# 3. Run the synthesis:
python synthesis/synthesize_offspring.py \
    parents/alphacaller \
    parents/yieldrotator \
    offspring/run_001

# 4. Inspect the output:
ls offspring/run_001/
#   SOUL.md
#   MEMORY.md
#   USER.md
#   cron_jobs.json
#   MATING_MANIFEST.md
#   raw_manifest.json

# 5. Read MATING_MANIFEST.md first (offspring name, ticker, locked niche, synthesis notes).
# Then read SOUL.md to see what voice and identity the synthesis produced.
# Then check cron_jobs.json to see which custom crons were inherited and which were dropped.
```

### Alternative providers

If OpenRouter rate-limits you or you want to use a different free gateway:

```bash
export BLENDER_SYNTH_BASE_URL=https://your.gateway.example/v1
export BLENDER_SYNTH_API_KEY=...
export BLENDER_SYNTH_MODEL=your-model-id
python synthesis/synthesize_offspring.py parents/alphacaller parents/yieldrotator offspring/run_002
```

Any OpenAI-compatible chat-completions endpoint works (Nous Portal, Together, NovitaAI, MiMo, NVIDIA NIM, custom).

## How to iterate

Re-run with different output directories (`offspring/run_001`, `run_002`, etc.) to see how stable the synthesis is. Typical workflow:

1. Run synthesis 3 times against the same parent pair. Compare outputs. They should rhyme (same locked_niche, similar voice, similar inherited crons) even if specific wording varies.
2. Pick the cleanest output as the reference. If all 3 are bad, the prompt in `synthesize_offspring.py` needs tuning - edit the `SYNTHESIS_INSTRUCTIONS` constant.
3. Hand-edit one parent to be more extreme (e.g., flip alphacaller's voice to be flowery instead of terse). Re-run. Check the offspring's voice rubric shifts accordingly.
4. Try a third seed parent (replace one) to map the synthesis's behavior across niche combinations.

## What this test does NOT do

- Does not deploy a running Hermes Agent daemon. The offspring's files are written to disk; nothing is launched.
- Does not register a Clawnch token, fund a Bankr wallet, or stand up an x402 endpoint. The crypto stack is not exercised.
- Does not post to Farcaster, X, or any social channel.
- Does not run any of the 12 Tier-1 archetypes' actual revenue logic. The crons are inert prompts.

Those next steps require the 6 custom MCP servers (`bankr-mcp`, `clawnch-mcp`, `x402-mcp`, `farcaster-mcp`, `registry-mcp`, `moltbook-mcp`). Build those after this synthesis pipeline produces consistently coherent offspring across at least 5 successful test runs.

## Failure modes to watch for

- **JSON parse failure**: the LLM wrapped its output in markdown despite the instructions, or hallucinated extra commentary. The script saves the raw text to `<output>_RAW_FAILED.txt`. Inspect, refine prompt, re-run.
- **Missing immutable LAYER 0**: the validation step catches this. The model dropped the terminal-goal text. Re-run with a stricter prompt or add a post-process step that pastes Layer 0 back in.
- **Tier-1 hygiene cron missing**: validation also catches this. The model invented its own cron schedule. Re-run.
- **Output is just a copy of one parent**: prompt needs more emphasis on niche-aware blending. Edit `SYNTHESIS_INSTRUCTIONS`.
- **Rate limit on free tier**: switch to a paid model temporarily (e.g., `nousresearch/hermes-4-llama-3.1-70b` at $0.13/$0.40 per M tokens, ~$0.05 per synthesis).
