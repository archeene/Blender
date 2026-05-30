# Plan: Hyperliquid trading agent (first Gen 0 founder, real-money test)

## Goal

Stand up the Blender protocol's first Gen 0 founder agent: a systematic
trend-following perpetuals trader on Hyperliquid that runs autonomously on
Fly.io (new "Tobias Wade / personal" account), holds a trade-only key,
respects code-enforced risk limits, and once live funds its $TOKEN_SELF
buy-and-burn from realized trading P&L. Testnet first, then mainnet $50.

## Locked decisions (operator, 2026-05-30)

- **Strategy**: systematic trend-following. Price vs N-period moving average +
  momentum. The LLM executes, monitors, and handles exceptions, but entries
  and exits follow the rule. Interpretable: strategy-followed is
  distinguishable from LLM-nonsense.
- **Rollout**: Hyperliquid testnet first (fake money, prove the loop), then
  mainnet with $50.
- **Risk preset (MODERATE)**: max 3x leverage, $40 max per position, $60 max
  total exposure, $25 daily-loss circuit breaker, markets BTC + ETH + SOL.

## Safety architecture (verified facts, not assumptions)

Verified 2026-05-30 against Hyperliquid docs + the official Python SDK:

- **Agent/API wallets are trade-only**: they can place and cancel orders but
  CANNOT withdraw funds. Source: hyperliquid.gitbook.io nonces-and-api-wallets
  + hyperliquid-python-sdk `approve_agent()`.
- **Testnet exists**: api.hyperliquid-testnet.xyz.
- **Official SDK**: `hyperliquid-python-sdk` (github.com/hyperliquid-dex/hyperliquid-python-sdk).

Two-key model:

- **MASTER wallet**: operator's own wallet (MetaMask / hardware). Holds USDC +
  withdrawal rights. Its key NEVER touches the server. Used once to deposit
  funds and call `approve_agent()`.
- **AGENT wallet**: minted via `approve_agent()`. Trade-only private key. This
  is the ONLY key on the Fly volume. Blast radius if it leaks, is prompt-
  injected, or the agent goes rogue = bad trades up to the deposited balance,
  never a drain to an external address.

Code-enforced risk limits live in `hyperliquid_mcp.py`, NOT in the LLM's
discretion. Every order passes hard checks; violations are rejected
regardless of what the model requests:

- market whitelist (BTC / ETH / SOL only; reject everything else)
- max leverage 3x (MCP sets leverage and refuses higher)
- max position notional $40
- max total exposure $60 across positions
- daily-loss circuit breaker $25: track realized + unrealized P&L since UTC
  midnight; once tripped, reject all opening orders (reduce-only still
  allowed) until next UTC day
- `HYPERLIQUID_TRADING_ENABLED` gate, defaults FALSE: agent runs read-only
  (signals + logging, no orders) until the operator explicitly enables
- `HYPERLIQUID_NETWORK` testnet|mainnet, defaults testnet
- kill switch: `emergency_halt()` cancels all open orders and locks to
  reduce-only

Honest framing recorded in SOUL.md: an LLM has no demonstrated edge at
discretionary leveraged trading. Test #1 success = the loop survives, the
limits hold, the key stays safe. Profit is a bonus, not the metric.

## Interface specification

### New MCP: `agent-template/mcp/hyperliquid_mcp.py`

Wraps `hyperliquid-python-sdk`. Tools:

- `get_account_state()` -> balance, margin, open positions
- `get_market_data(coin)` -> mark price, funding, open interest, recent candles
- `get_trend_signal(coin, ma_period=24, momentum_lookback=12)` -> {signal:
  long|short|flat, ma, momentum, price} (computes the systematic rule)
- `set_leverage(coin, leverage)` -> enforces <= HL_MAX_LEVERAGE
- `place_order(coin, is_buy, size_usd, order_type='market', reduce_only=False)`
  -> runs ALL hard checks, rejects violations with an explicit reason
- `close_position(coin)`
- `cancel_all()`
- `get_open_positions()`
- `get_daily_pnl()` -> realized + unrealized since UTC midnight
- `emergency_halt()` -> cancel all + reduce-only lock
- `risk_limits()` -> returns the active limit config (diagnostic; proves what
  the agent is actually constrained by)

Env vars: HYPERLIQUID_AGENT_KEY, HYPERLIQUID_MASTER_ADDRESS,
HYPERLIQUID_NETWORK, HYPERLIQUID_TRADING_ENABLED, HL_MAX_LEVERAGE,
HL_MAX_POSITION_USD, HL_MAX_EXPOSURE_USD, HL_DAILY_LOSS_LIMIT_USD,
HL_MARKET_WHITELIST. Defaults bake in the moderate preset; gracefully skips
(read-only) when HYPERLIQUID_AGENT_KEY is unset.

### New founder agent: `founders/hyperliquid-trader/`

Gen 0 founder, hand-authored (no synthesis). Files:

- `SOUL.md` -> niche defi_auto_trader; terminal goal maximize $TOKEN_SELF via
  trading-P&L buy-and-burn; LAYER 1 identity; LAYER 2 carries the systematic
  trend rule + the honest risk framing + the social progression ladder.
- `MEMORY.md` -> numerical risk-aware voice rubric, trading vocab, the rule
  parameters, empty lessons.
- `USER.md` -> self-model + operational state (wallet, runway, status NEWBORN).
- `cron_jobs.json` -> trend_scan (15m), trade_decision (hourly), position_monitor
  (5m), risk_circuit_check (5m), plus standard hygiene (protocol_sync,
  monitoring_scan, nightly_triage, weekly_planning, weekly_reflection),
  death_check, social_posting hooks, clawnch_launch, publish_profile.
- `config.yaml` -> agent-template config + the hyperliquid MCP server entry.
- `fly_deploy/` -> Dockerfile (adds hyperliquid-python-sdk), fly.toml (new
  account, app blender-hyperliquid-trader), entrypoint.

### New skill: `agent-template/skills/hyperliquid_trade.md`

The trend-following decision workflow: get_trend_signal -> check circuit
breaker -> size within limits -> place_order (reduce-only when in drawdown)
-> log every decision -> post notable trades to social. Pinned in
bootstrap_crons.py.

### Tests: `reproduction-test/tests/test_hyperliquid_limits.py`

Mock the SDK; prove the code-enforced limits REJECT: over-leverage, over-size,
over-exposure, non-whitelisted market, opens while the circuit breaker is
tripped. Prove reduce-only is still allowed in breaker state. This is the
single most important test: it proves the safety net works without touching
the real API or any real money.

## Verification strategy

1. `test_hyperliquid_limits.py` all green (mocked) -> every out-of-bounds order
   is rejected with an explicit reason.
2. `run_all.py` still green -> no regression to the existing 48 tests.
3. `hyperliquid_mcp.py` imports cleanly (ast.parse + import smoke).
4. Fly app created on the new account (`flyctl apps list` shows it).
5. Testnet smoke deploy: agent computes signals, places a real TESTNET order,
   circuit breaker fires when tripped, death_check + crons run. Confirm by
   reading Fly logs.
6. ONLY after testnet smoke passes + operator confirms: flip
   HYPERLIQUID_NETWORK=mainnet, fund $50, set HYPERLIQUID_TRADING_ENABLED=true.

## Proof of done (build phase, before any live trading)

```
$ python reproduction-test/tests/run_all.py
... test_hyperliquid_limits passing, existing suites green ...
$ python -c "import ast; ast.parse(open('agent-template/mcp/hyperliquid_mcp.py').read())"
$ flyctl apps list   # shows blender-hyperliquid-trader
```

## Out of scope (this build)

- Live mainnet trading (separate, explicitly gated step; operator confirms
  after testnet smoke passes).
- The master-wallet funding + approve_agent ceremony (operator does this once
  with their own wallet; I provide an exact one-shot script + steps).
- Profitability tuning of the strategy (test #1 proves the loop, not the edge).
- Vault / deposit-from-others features.
- Markets beyond BTC / ETH / SOL.

## Operator actions required (I cannot do these)

1. Control a real wallet (MetaMask / hardware) = the MASTER. Never share its key.
2. Testnet first: get testnet USDC from the Hyperliquid testnet faucet, then
   run the `approve_agent` ceremony (I provide a one-shot script) to mint the
   trade-only AGENT key.
3. Provide the AGENT key + master address as Fly secrets (I set them via
   flyctl with the stored token, or you set them yourself).
4. Mainnet (later): deposit $50 USDC to Hyperliquid, approve a mainnet agent
   wallet, set the mainnet secrets, then give the explicit go to enable live
   trading.
