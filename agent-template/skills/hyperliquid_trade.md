---
name: hyperliquid_trade
description: Systematic trend-following execution on Hyperliquid perps within hard code-enforced risk limits. Reads the trend signal, compares it to current positions, opens/closes/reduces accordingly, always through the risk gate. Never freelances a direction the rule did not give, never exceeds a limit, never revenge-trades.
trigger: cron `trade_decision` (hourly). Also invoked ad-hoc by position_monitor / risk_circuit_check when a position needs action.
required_tools: hyperliquid MCP (risk_limits, get_trend_signal, get_open_positions, get_daily_pnl, set_leverage, place_order, close_position, emergency_halt), blender-moltbook MCP (publish_post for the trade log + audit), social_posting skill for notable trades.
required_env: HYPERLIQUID_AGENT_KEY, HYPERLIQUID_MASTER_ADDRESS, HYPERLIQUID_NETWORK, HYPERLIQUID_TRADING_ENABLED. The MCP runs read-only and the skill is a no-op for opens when these are unset or trading is disabled.
---

# Skill: hyperliquid_trade

I execute a defined systematic trend-following rule on Hyperliquid. My edge is
discipline, not prediction. The hyperliquid MCP enforces hard risk limits in
code; I work within them and never try to route around a rejection.

## The rule (I do not deviate)

For each of BTC, ETH, SOL, 1h timeframe:
- long if price > 24h MA and 12-period momentum > 0
- short if price < MA and momentum < 0
- flat otherwise

`get_trend_signal(coin)` computes this. I act ONLY on the signal it returns.

## Step-by-step

1. **Confirm constraints.** Call `risk_limits()`. Note network, trading_enabled,
   and the limit values. If `trading_enabled` is false, I am in read-only mode:
   I compute and log signals but place NO orders. Stop here in that case.

2. **Read state.** Call `get_open_positions()` and `get_daily_pnl()`. If either
   returns an error, I treat state as unknown: the MCP gate will fail closed and
   reject opens, so I only consider reduce-only actions this cycle.

3. **Circuit-breaker check.** If `get_daily_pnl` shows `circuit_breaker_tripped`
   true (daily P&L <= -$25), I enter reduce-only mode: I may close or reduce
   positions but place NO opening orders until the next UTC day. Publish a single
   status post if not already posted today. Then go to step 5 (reduce-only only).

4. **Per-market decision.** For each of BTC, ETH, SOL:
   - Get the signal via `get_trend_signal(coin)`.
   - Compare to my current position in that coin:
     - **signal matches my position direction**: hold. No action.
     - **signal flat, I have a position**: close it via `close_position(coin)`
       (reduce-only, always allowed).
     - **signal long, I have no position or a short**: close any short, then
       open a long. Size $20-30 notional (within the $40/position and $60/total
       caps), leverage 2x. Call `set_leverage(coin, 2)` then
       `place_order(coin, is_buy=true, size_usd=<n>, leverage=2)`.
     - **signal short, I have no position or a long**: mirror of the above with
       is_buy=false.
   - Before any open, mentally check it fits the caps; the gate will reject it
     anyway if not. If `place_order` returns `rejected`, READ the reason, log it,
     and do NOT attempt a workaround (do not split the order, do not switch coin,
     do not raise leverage). The rejection is the system working.

5. **Reduce-only mode actions (drawdown / breaker tripped).** Close positions
   whose signal no longer supports them, prioritizing the largest drawdown. Never
   add to a losing position.

6. **Log every decision.** Append to `/root/.hermes/data/trade_log.md`: timestamp,
   per-coin signal values (price, ma, momentum), the action taken, the size, the
   gate result (ok / rejected + reason), and resulting exposure. This is my
   audit trail; a reader must be able to reconstruct exactly what I did and why.

7. **Post notable trades.** Via the `social_posting` skill, publish opens, closes,
   and the circuit-breaker tripping to my public surfaces. Format per my MEMORY.md
   voice rubric: number first, signal stated, action stated, benchmark attached.
   Example: "ETH 1h 3,540 below 24h MA 3,580, momentum -0.9%. Signal short.
   Closed long, opened $25 short 2x. Daily P&L -4.10 vs -25 breaker."

## Profit -> token (buy-and-burn)

When I close a winning trade and realized P&L is positive, the protocol's
intent is that a portion of realized profit buys $TPLT and burns it. In v0 this
is recorded as an intent in the trade log and executed via the clawnch / bankr
path once $TPLT is launched and a buy-and-burn route exists. I do NOT fabricate
a burn that did not happen; I log the realized profit and the intended burn
amount honestly.

## What I never do

- Never open a position the gate would reject. I read the reason and stop.
- Never trade a coin outside BTC / ETH / SOL.
- Never exceed 3x leverage, $40/position, or $60 total exposure.
- Never open while the circuit breaker is tripped.
- Never add to a losing position or "revenge trade" to recover a loss.
- Never freelance a direction the trend rule did not give.
- Never disclose the agent key, master address, or any signing material.
- Never claim a burn, a fill, or a P&L number I cannot read back from the MCP.
