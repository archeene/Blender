"""Smoke tests for the Hyperliquid risk-limit safety net.

The whole point of these tests: prove the code-enforced limits reject every
out-of-bounds order WITHOUT touching the real API, the SDK, or any money.
check_order_allowed and compute_trend_signal are pure functions, so this runs
offline and deterministically.

Run:
    python reproduction-test/tests/test_hyperliquid_limits.py

Exit: 0 = all pass, 1 = failure, 2 = harness error.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "agent-template" / "mcp"))

try:
    import hyperliquid_mcp as hl  # noqa: E402
except Exception as e:  # pragma: no cover
    print(f"[test_hyperliquid_limits] ERROR importing hyperliquid_mcp: {e}", file=sys.stderr)
    sys.exit(2)


# Moderate preset, used explicitly so the tests don't depend on env vars.
LIMITS = {
    "network": "testnet",
    "trading_enabled": True,
    "max_leverage": 3,
    "max_position_usd": 40,
    "max_exposure_usd": 60,
    "daily_loss_limit_usd": 25,
    "market_whitelist": ["BTC", "ETH", "SOL"],
}

_results = []


def _t(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    _results.append((status, name, detail))
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail and not cond else ""))


def allowed(**kw):
    """check_order_allowed with sane defaults for a within-limits open."""
    base = dict(
        coin="BTC", size_usd=20, leverage=2, reduce_only=False,
        open_positions=[], daily_pnl_usd=0.0, limits=LIMITS, trading_enabled=True,
    )
    base.update(kw)
    return hl.check_order_allowed(**base)


def run_tests():
    print("== check_order_allowed: gate ==")
    ok, reason = allowed()
    _t("within-limits open is allowed", ok, reason)

    ok, reason = allowed(trading_enabled=False)
    _t("trading disabled blocks all orders", not ok and "trading_disabled" in reason, reason)

    ok, reason = allowed(coin="DOGE")
    _t("non-whitelisted market rejected", not ok and "market_not_whitelisted" in reason, reason)

    ok, reason = allowed(size_usd=0)
    _t("zero size rejected", not ok and "invalid_size" in reason, reason)

    ok, reason = allowed(size_usd=-5)
    _t("negative size rejected", not ok and "invalid_size" in reason, reason)

    ok, reason = allowed(leverage=5)
    _t("leverage over cap rejected", not ok and "leverage_exceeded" in reason, reason)

    ok, reason = allowed(leverage=3)
    _t("leverage at exactly the cap allowed", ok, reason)

    print("\n== per-position + exposure caps ==")
    ok, reason = allowed(size_usd=41)
    _t("position over $40 rejected", not ok and "position_too_large" in reason, reason)

    ok, reason = allowed(size_usd=40)
    _t("position at exactly $40 allowed", ok, reason)

    ok, reason = allowed(size_usd=30, open_positions=[{"coin": "ETH", "notional_usd": 40}])
    _t("exposure over $60 rejected (40 existing + 30 new)", not ok and "exposure_exceeded" in reason, reason)

    ok, reason = allowed(size_usd=20, open_positions=[{"coin": "ETH", "notional_usd": 40}])
    _t("exposure at exactly $60 allowed (40 + 20)", ok, reason)

    print("\n== daily-loss circuit breaker ==")
    ok, reason = allowed(daily_pnl_usd=-25)
    _t("breaker trips at exactly -$25 (blocks opens)", not ok and "circuit_breaker_tripped" in reason, reason)

    ok, reason = allowed(daily_pnl_usd=-30)
    _t("breaker blocks opens past -$25", not ok and "circuit_breaker_tripped" in reason, reason)

    ok, reason = allowed(daily_pnl_usd=-24.99)
    _t("just under the breaker still opens", ok, reason)

    print("\n== reduce-only bypasses opening checks (lowers risk) ==")
    ok, reason = allowed(reduce_only=True, daily_pnl_usd=-100, open_positions=[{"coin": "BTC", "notional_usd": 60}], size_usd=50)
    _t("reduce-only allowed even when breaker tripped + over exposure", ok and "reduce_only" in reason, reason)

    ok, reason = allowed(reduce_only=True, coin="DOGE")
    _t("reduce-only still rejects non-whitelisted market", not ok and "market_not_whitelisted" in reason, reason)

    ok, reason = allowed(reduce_only=True, leverage=9)
    _t("reduce-only still rejects over-leverage", not ok and "leverage_exceeded" in reason, reason)

    print("\n== fail-closed when state unknown ==")
    ok, reason = allowed(daily_pnl_usd=None)
    _t("open rejected when daily P&L unknown (fail closed)", not ok and "fail_closed" in reason, reason)

    ok, reason = allowed(open_positions=None)
    _t("open rejected when positions unknown (fail closed)", not ok and "fail_closed" in reason, reason)

    ok, reason = allowed(reduce_only=True, daily_pnl_usd=None, open_positions=None)
    _t("reduce-only allowed even when state unknown", ok, reason)

    print("\n== compute_trend_signal ==")
    # rising series: price above MA, positive momentum -> long
    rising = [100 + i for i in range(40)]
    sig = hl.compute_trend_signal(rising, ma_period=24, momentum_lookback=12)
    _t("rising series -> long", sig["signal"] == "long", str(sig))

    falling = [200 - i for i in range(40)]
    sig = hl.compute_trend_signal(falling, ma_period=24, momentum_lookback=12)
    _t("falling series -> short", sig["signal"] == "short", str(sig))

    flat_series = [150] * 40
    sig = hl.compute_trend_signal(flat_series, ma_period=24, momentum_lookback=12)
    _t("flat series -> flat", sig["signal"] == "flat", str(sig))

    sig = hl.compute_trend_signal([100, 101, 102], ma_period=24, momentum_lookback=12)
    _t("insufficient data -> flat with reason", sig["signal"] == "flat" and "insufficient_data" in sig.get("reason", ""), str(sig))

    print("\n== active_limits / risk_limits reflect defaults ==")
    lim = hl.active_limits()
    _t("default whitelist is BTC/ETH/SOL", set(lim["market_whitelist"]) == {"BTC", "ETH", "SOL"}, str(lim["market_whitelist"]))
    _t("default trading disabled (read-only)", lim["trading_enabled"] is False, str(lim["trading_enabled"]))
    _t("default network testnet", lim["network"] == "testnet", str(lim["network"]))


def main():
    print("Running Hyperliquid risk-limit safety-net tests...\n")
    run_tests()
    print()
    passed = sum(1 for s, _, _ in _results if s == "PASS")
    failed = sum(1 for s, _, _ in _results if s == "FAIL")
    print(f"Result: {passed} passed, {failed} failed (total {len(_results)})")
    if failed:
        print("\nFailed cases:")
        for s, name, detail in _results:
            if s == "FAIL":
                print(f"  - {name}: {detail}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
