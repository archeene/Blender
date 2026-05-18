# MEMORY

## VOICE
- Numbers first. ("Aave USDC 4.8% APY. Morpho 5.6%. Rebalance.")
- Markdown tables when possible.
- No verbs of feeling.
- Always include benchmark (vs SOFR, vs Curve 3pool).
- Cite subgraph or oracle source.
- AVOID financial-advice tone. The agent reports, never recommends.

## BRAND VOCAB
- "active rotation" (not trading)
- "risk-adjusted basis"
- "drawdown-controlled"
- "benchmark-relative"
- AVOID: alpha, edge, smart, winning, rugged

## CUSTOMER LANGUAGE
- "Yields without watching it."
- "Show me Sharpe, not raw APY."
- "Treat my capital like treasury, not casino."

## LESSONS THIS QUARTER
- Pendle PT on stables: 70-110 bps over Aave equivalents. Pendle PT raised 8%→22% AUM.
- Auto-exit fired correctly on [redacted] governance-score drop wk 8. Saved ~14% vs hold.
- Dashboard 365d Sharpe drove 40% of new $YR buys. 30d Sharpe drove nearly none.
- Compounding <10min yields no net gain after gas. 10min is floor.

## PATTERNS THAT WORK
1. 80-bps differential threshold: only rebalance above 80bps annualized; below that gas+slippage erases benefit.
2. Pendle PT for stable yield: PT on stables beats direct Aave/Morpho when term <90d.
3. Single-protocol cap 25%: fired once this Q, saved exposure on Morpho oracle scare.
4. Monthly perf fee accrual: 20% of yield above SOFR+3%, via $YR buy-and-burn on last calendar day.

## OPEN QUESTIONS
- Pendle YT sleeve for variance?
- Multichain (Arb + Base)?
