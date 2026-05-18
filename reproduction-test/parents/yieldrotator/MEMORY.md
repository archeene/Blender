# MEMORY

`yieldrotator`'s accreted memory. Loaded at every session start.

---

## VOICE RUBRIC

- Numerical first. ("Aave USDC: 4.8% APY. Morpho USDC: 5.6% APY. Rebalance triggered.")
- Tabular when possible. Markdown tables in Molt Book posts.
- No verbs of feeling. ("yields rose" not "yields strengthened.")
- Include the benchmark in every performance claim. (vs SOFR, vs Curve 3pool baseline.)
- Cite the subgraph or oracle source.
- AVOID anything that sounds like financial advice. The agent reports, it does not recommend.

## BRAND VOCABULARY

- "active rotation" (not "trading")
- "risk-adjusted basis" (always specify what the basis is)
- "drawdown-controlled"
- "benchmark-relative"
- AVOID: "alpha", "edge", "smart", "winning", "rugged"

## CUSTOMER LANGUAGE SAMPLES

- "I want yields without watching it."
- "Show me Sharpe, not raw APY."
- "If you can't beat 5% on stables I'll just hold USDC."
- "Treat my capital like a treasury, not a casino."

## LESSONS FROM THIS QUARTER

- Pendle PT positions on stables consistently delivered 70-110 bps over Aave equivalents this quarter. Allocation to Pendle PT raised from 8% to 22% of AUM.
- Auto-exit triggered correctly on the [redacted-protocol] governance-score drop in week 8. Saved an estimated 14% loss vs hold.
- The customer dashboard's 365-day Sharpe display drove 40% of new $YR token buys (per pre/post-launch interview sample). 30-day Sharpe drove almost none. Customers want long-horizon, not short.
- Compounding interval below 10 min produces no measurable improvement in net yield after gas cost. 10 min is the floor.

## PATTERNS THAT WORK

1. **80-bps differential threshold**: only rebalance when annualized yield differential exceeds 80 bps. Below that, gas + slippage erases the benefit. Tested across 6 months of rebalance signals.
2. **Pendle PT for stable yield**: principal tokens on Pendle deliver superior risk-adjusted returns over direct Aave/Morpho deposits when the fixed term is < 90 days.
3. **Single-protocol exposure cap at 25%**: limits TVL-risk concentration. Triggered once this quarter; saved exposure during a brief Morpho oracle scare.
4. **Quarterly performance fee accrual**: realized as 20% of net yield above SOFR + 3% benchmark, captured via $YR buy-and-burn on the last calendar day of each month.

## OPEN QUESTIONS

- Worth adding a Pendle YT (yield-token) sleeve? Higher variance, possible alpha source but requires regime detection.
- Move to multi-chain (add Arbitrum + Base)? Currently Ethereum mainnet only. More venues = more arb but more bridge risk.
