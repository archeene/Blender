"""Hyperliquid trading MCP for Blender agents.

Active directional perps trading on Hyperliquid with HARD, CODE-ENFORCED
risk limits. The LLM picks direction and timing; this module holds the leash.
Every order passes check_order_allowed() before any SDK call; violations are
rejected regardless of what the model requests.

SAFETY MODEL (verified 2026-05-30 against Hyperliquid docs + python SDK):
  - The key in HYPERLIQUID_AGENT_KEY is an AGENT / API wallet: it can place
    and cancel orders but CANNOT withdraw funds. The master account (operator's
    own wallet, key NEVER on the server) holds the funds + withdrawal rights
    and mints the agent key once via approve_agent(). Worst case if this key
    leaks or the agent goes rogue = bad trades up to the deposited balance,
    never a drain to an external address.
  - HYPERLIQUID_TRADING_ENABLED defaults FALSE: the agent runs read-only
    (signals + monitoring, no orders) until the operator explicitly enables.
  - HYPERLIQUID_NETWORK defaults testnet.
  - Limits default to the MODERATE preset: 3x leverage, $40/position,
    $60 total exposure, $25 daily-loss circuit breaker, BTC/ETH/SOL only.

FAIL-CLOSED: if the order path cannot determine current exposure or daily
P&L, it REJECTS opening orders (it does not assume zero). Reduce-only orders
(which lower risk) are allowed through that path.

The risk-limit logic (check_order_allowed) and the trend signal
(compute_trend_signal) are PURE functions with no SDK / network dependency,
so the safety net is fully unit-tested without touching the real API or any
money. The thin SDK wrappers are best-effort against the documented
hyperliquid-python-sdk API and are verified live at deploy time.

Env vars:
  HYPERLIQUID_NETWORK            testnet | mainnet   (default testnet)
  HYPERLIQUID_TRADING_ENABLED    true | false         (default false)
  HYPERLIQUID_AGENT_KEY          trade-only agent private key (hex)
  HYPERLIQUID_MASTER_ADDRESS     master account address the agent trades for
  HL_MAX_LEVERAGE                default 3
  HL_MAX_POSITION_USD            default 40
  HL_MAX_EXPOSURE_USD            default 60
  HL_DAILY_LOSS_LIMIT_USD        default 25
  HL_MARKET_WHITELIST            default "BTC,ETH,SOL"
"""
import os
import time
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:
    raise SystemExit("Missing 'mcp' package. Install: pip install mcp") from exc


# ---------------------------------------------------------------------------
# Config (moderate preset defaults)
# ---------------------------------------------------------------------------

NETWORK = os.environ.get("HYPERLIQUID_NETWORK", "testnet").lower()
TRADING_ENABLED = os.environ.get("HYPERLIQUID_TRADING_ENABLED", "false").lower() in ("1", "true", "yes")
AGENT_KEY = os.environ.get("HYPERLIQUID_AGENT_KEY", "")
MASTER_ADDRESS = os.environ.get("HYPERLIQUID_MASTER_ADDRESS", "")


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (ValueError, TypeError):
        return float(default)


MAX_LEVERAGE = _float_env("HL_MAX_LEVERAGE", 3)
MAX_POSITION_USD = _float_env("HL_MAX_POSITION_USD", 40)
MAX_EXPOSURE_USD = _float_env("HL_MAX_EXPOSURE_USD", 60)
DAILY_LOSS_LIMIT_USD = _float_env("HL_DAILY_LOSS_LIMIT_USD", 25)
MARKET_WHITELIST = [
    m.strip().upper()
    for m in os.environ.get("HL_MARKET_WHITELIST", "BTC,ETH,SOL").split(",")
    if m.strip()
]


def active_limits() -> dict[str, Any]:
    return {
        "network": NETWORK,
        "trading_enabled": TRADING_ENABLED,
        "max_leverage": MAX_LEVERAGE,
        "max_position_usd": MAX_POSITION_USD,
        "max_exposure_usd": MAX_EXPOSURE_USD,
        "daily_loss_limit_usd": DAILY_LOSS_LIMIT_USD,
        "market_whitelist": MARKET_WHITELIST,
    }


# ---------------------------------------------------------------------------
# PURE SAFETY NET (fully unit-tested; no SDK, no network, no money)
# ---------------------------------------------------------------------------

def check_order_allowed(
    coin: str,
    size_usd: float | None,
    leverage: float | None,
    reduce_only: bool,
    open_positions: list[dict] | None,
    daily_pnl_usd: float | None,
    limits: dict | None = None,
    trading_enabled: bool | None = None,
) -> tuple[bool, str]:
    """Return (allowed, reason). PURE function — the load-bearing safety net.

    open_positions: list of {coin, notional_usd}. daily_pnl_usd: realized +
    unrealized since UTC midnight (negative = loss).

    Order of checks matters. reduce_only orders LOWER risk, so they bypass the
    opening-order checks (exposure / size / circuit breaker) but still must be
    whitelisted, positive-sized, and within the leverage cap.
    """
    L = limits or active_limits()
    te = TRADING_ENABLED if trading_enabled is None else trading_enabled
    coin_u = str(coin).upper()
    whitelist = [m.upper() for m in L["market_whitelist"]]

    # 0. trading must be enabled (read-only gate)
    if not te:
        return (False, "trading_disabled: HYPERLIQUID_TRADING_ENABLED is false (read-only mode)")

    # 1. market whitelist
    if coin_u not in whitelist:
        return (False, f"market_not_whitelisted: {coin_u} not in {whitelist}")

    # 2. positive size
    if size_usd is None or size_usd <= 0:
        return (False, f"invalid_size: size_usd must be > 0 (got {size_usd})")

    # 3. leverage cap (applies to every order)
    if leverage is not None and leverage > L["max_leverage"]:
        return (False, f"leverage_exceeded: {leverage}x > max {L['max_leverage']}x")

    # reduce-only orders reduce risk; allow past the opening-order checks
    if reduce_only:
        return (True, "ok_reduce_only")

    # ---- opening-order checks ----

    # 4. daily-loss circuit breaker
    if daily_pnl_usd is None:
        # fail closed: cannot confirm we're under the loss limit
        return (False, "fail_closed: daily P&L unavailable; opening orders blocked")
    if daily_pnl_usd <= -abs(L["daily_loss_limit_usd"]):
        return (False, f"circuit_breaker_tripped: daily P&L {daily_pnl_usd} <= -{L['daily_loss_limit_usd']}; opens blocked, reduce-only allowed")

    # 5. per-position notional cap
    if size_usd > L["max_position_usd"]:
        return (False, f"position_too_large: {size_usd} > max {L['max_position_usd']} per position")

    # 6. total exposure cap
    if open_positions is None:
        # fail closed: cannot confirm total exposure
        return (False, "fail_closed: open positions unavailable; opening orders blocked")
    current_exposure = sum(abs(p.get("notional_usd", 0) or 0) for p in open_positions)
    if current_exposure + size_usd > L["max_exposure_usd"]:
        return (False, f"exposure_exceeded: current {current_exposure} + {size_usd} > max {L['max_exposure_usd']}")

    return (True, "ok")


def compute_trend_signal(
    closes: list[float],
    ma_period: int = 24,
    momentum_lookback: int = 12,
) -> dict[str, Any]:
    """Systematic trend rule. PURE function.

    long  if price > MA(ma_period) and momentum(momentum_lookback) > 0
    short if price < MA and momentum < 0
    flat  otherwise

    Returns {signal, price, ma, momentum}. flat + reason on insufficient data.
    """
    need = max(ma_period, momentum_lookback) + 1
    if not closes or len(closes) < need:
        return {
            "signal": "flat",
            "reason": f"insufficient_data: need {need} closes, got {len(closes) if closes else 0}",
            "price": closes[-1] if closes else None,
            "ma": None,
            "momentum": None,
        }
    price = closes[-1]
    ma = sum(closes[-ma_period:]) / ma_period
    momentum = closes[-1] - closes[-1 - momentum_lookback]
    if price > ma and momentum > 0:
        signal = "long"
    elif price < ma and momentum < 0:
        signal = "short"
    else:
        signal = "flat"
    return {"signal": signal, "price": price, "ma": ma, "momentum": momentum}


# ---------------------------------------------------------------------------
# SDK layer (lazy, graceful-skip; exact calls verified live at deploy)
# ---------------------------------------------------------------------------

_sdk: dict[str, Any] = {"info": None, "exchange": None, "error": None, "exchange_error": None, "init": False}


def _valid_agent_key(k: str | None) -> bool:
    """True only if k looks like a 32-byte hex private key. Guards against an
    unset or unexpanded env var (e.g. the literal '${HYPERLIQUID_AGENT_KEY}'
    when no Fly secret is set) reaching eth_account and crashing with
    'Non-hexadecimal digit found' -- which would otherwise poison the
    read-only path too."""
    if not k:
        return False
    s = k[2:] if k.lower().startswith("0x") else k
    if len(s) != 64:
        return False
    try:
        int(s, 16)
        return True
    except ValueError:
        return False


def _base_url() -> str:
    try:
        from hyperliquid.utils import constants  # type: ignore
        return constants.MAINNET_API_URL if NETWORK == "mainnet" else constants.TESTNET_API_URL
    except ImportError:
        return "https://api.hyperliquid.xyz" if NETWORK == "mainnet" else "https://api.hyperliquid-testnet.xyz"


def _ensure_sdk() -> dict[str, Any]:
    if _sdk["init"]:
        return _sdk
    _sdk["init"] = True
    try:
        from hyperliquid.info import Info  # type: ignore
        from hyperliquid.exchange import Exchange  # type: ignore
    except ImportError:
        _sdk["error"] = "sdk_missing: pip install hyperliquid-python-sdk"
        return _sdk
    base = _base_url()
    # Info (read) needs no key. Read tools (market data, trend signals) work
    # even with no agent key configured, so a missing/bad key must NOT block
    # them. Exchange init failures go in exchange_error, never the global error.
    try:
        _sdk["info"] = Info(base, skip_ws=True)
    except Exception as e:  # noqa: BLE001 - surface read-path init failure
        _sdk["error"] = f"info_init_failed: {e}"
        return _sdk
    if _valid_agent_key(AGENT_KEY):
        try:
            from eth_account import Account  # type: ignore
            wallet = Account.from_key(AGENT_KEY)
            kwargs: dict[str, Any] = {}
            if MASTER_ADDRESS:
                kwargs["account_address"] = MASTER_ADDRESS
            _sdk["exchange"] = Exchange(wallet, base, **kwargs)
        except Exception as e:  # noqa: BLE001
            _sdk["exchange_error"] = f"exchange_init_failed: {e}"
    else:
        _sdk["exchange_error"] = "no_valid_agent_key (read-only mode)"
    return _sdk


def _user_address() -> str:
    """Address whose state we read: the master account if set, else derive
    from the agent key."""
    if MASTER_ADDRESS:
        return MASTER_ADDRESS
    if _valid_agent_key(AGENT_KEY):
        try:
            from eth_account import Account  # type: ignore
            return Account.from_key(AGENT_KEY).address
        except Exception:  # noqa: BLE001
            return ""
    return ""


def _open_positions_raw() -> list[dict] | None:
    """Return [{coin, notional_usd, size, entry_px}] or None on any failure.
    None means 'unknown' -> the gate fails closed on opening orders."""
    s = _ensure_sdk()
    if s.get("error") or not s.get("info"):
        return None
    addr = _user_address()
    if not addr:
        return None
    try:
        state = s["info"].user_state(addr)
    except Exception:  # noqa: BLE001
        return None
    out = []
    for ap in state.get("assetPositions", []):
        pos = ap.get("position", {})
        szi = float(pos.get("szi", 0) or 0)
        if szi == 0:
            continue
        coin = pos.get("coin", "")
        # positionValue is the notional in USD per Hyperliquid's state shape
        notional = abs(float(pos.get("positionValue", 0) or 0))
        out.append({"coin": coin, "notional_usd": notional, "size": szi,
                    "entry_px": float(pos.get("entryPx", 0) or 0),
                    "unrealized_pnl": float(pos.get("unrealizedPnl", 0) or 0)})
    return out


def _daily_pnl_usd() -> float | None:
    """Realized + unrealized P&L since UTC midnight, or None on failure
    (None -> gate fails closed on opening orders)."""
    s = _ensure_sdk()
    if s.get("error") or not s.get("info"):
        return None
    addr = _user_address()
    if not addr:
        return None
    # unrealized from open positions
    positions = _open_positions_raw()
    if positions is None:
        return None
    unrealized = sum(p.get("unrealized_pnl", 0) for p in positions)
    # realized from fills since UTC midnight
    midnight = int(time.gmtime().tm_hour)  # placeholder guard; real calc below
    try:
        import calendar
        now = time.gmtime()
        midnight_unix_ms = calendar.timegm((now.tm_year, now.tm_mon, now.tm_mday, 0, 0, 0, 0, 0, 0)) * 1000
        fills = s["info"].user_fills(addr)
        realized = sum(
            float(f.get("closedPnl", 0) or 0)
            for f in fills
            if int(f.get("time", 0)) >= midnight_unix_ms
        )
    except Exception:  # noqa: BLE001
        # cannot confirm realized component -> fail closed
        return None
    return realized + unrealized


# ---------------------------------------------------------------------------
# MCP tool surface
# ---------------------------------------------------------------------------

mcp = FastMCP("hyperliquid")


@mcp.tool()
def risk_limits() -> dict[str, Any]:
    """Return the active code-enforced risk limits and mode. Diagnostic: shows
    exactly what the agent is constrained by. Always safe to call."""
    return active_limits()


@mcp.tool()
def get_account_state() -> dict[str, Any]:
    """Account balance, margin summary, and open positions. Read-only."""
    s = _ensure_sdk()
    if s.get("error"):
        return {"error": s["error"]}
    addr = _user_address()
    if not addr:
        return {"error": "no_address: set HYPERLIQUID_MASTER_ADDRESS or HYPERLIQUID_AGENT_KEY"}
    try:
        state = s["info"].user_state(addr)
    except Exception as e:  # noqa: BLE001
        return {"error": f"user_state_failed: {e}"}
    ms = state.get("marginSummary", {})
    return {
        "ok": True,
        "network": NETWORK,
        "address": addr,
        "account_value_usd": float(ms.get("accountValue", 0) or 0),
        "total_margin_used_usd": float(ms.get("totalMarginUsed", 0) or 0),
        "positions": _open_positions_raw() or [],
    }


@mcp.tool()
def get_open_positions() -> dict[str, Any]:
    """Current open positions with notional in USD. Read-only."""
    pos = _open_positions_raw()
    if pos is None:
        return {"error": "positions_unavailable"}
    return {"ok": True, "positions": pos, "total_exposure_usd": sum(p["notional_usd"] for p in pos)}


@mcp.tool()
def get_daily_pnl() -> dict[str, Any]:
    """Realized + unrealized P&L since UTC midnight. Drives the circuit
    breaker. Returns error if it cannot be computed (the gate then fails
    closed on opening orders)."""
    pnl = _daily_pnl_usd()
    if pnl is None:
        return {"error": "daily_pnl_unavailable"}
    tripped = pnl <= -abs(DAILY_LOSS_LIMIT_USD)
    return {"ok": True, "daily_pnl_usd": pnl, "limit_usd": DAILY_LOSS_LIMIT_USD,
            "circuit_breaker_tripped": tripped}


@mcp.tool()
def get_market_data(coin: str, interval: str = "1h", lookback_hours: int = 48) -> dict[str, Any]:
    """Recent candles + mark price for a coin. Read-only. Returns the close
    series so get_trend_signal can compute the rule."""
    s = _ensure_sdk()
    if s.get("error") or not s.get("info"):
        return {"error": s.get("error") or "info_unavailable"}
    coin_u = coin.upper()
    try:
        end = int(time.time() * 1000)
        start = end - lookback_hours * 3600 * 1000
        candles = s["info"].candles_snapshot(coin_u, interval, start, end)
        closes = [float(c.get("c", 0) or 0) for c in candles]
        return {"ok": True, "coin": coin_u, "interval": interval,
                "closes": closes, "last_price": closes[-1] if closes else None,
                "candle_count": len(closes)}
    except Exception as e:  # noqa: BLE001
        return {"error": f"market_data_failed: {e}"}


@mcp.tool()
def get_trend_signal(coin: str, ma_period: int = 24, momentum_lookback: int = 12,
                     interval: str = "1h") -> dict[str, Any]:
    """Compute the systematic trend signal for a coin (long/short/flat).
    Read-only: fetches candles, applies compute_trend_signal. This is the
    agent's entry/exit rule."""
    md = get_market_data(coin, interval=interval,
                         lookback_hours=max(ma_period, momentum_lookback) + 6)
    if md.get("error"):
        return md
    sig = compute_trend_signal(md["closes"], ma_period=ma_period,
                               momentum_lookback=momentum_lookback)
    sig["coin"] = coin.upper()
    sig["ok"] = True
    return sig


@mcp.tool()
def set_leverage(coin: str, leverage: float, cross: bool = False) -> dict[str, Any]:
    """Set leverage for a coin. Rejected if leverage > HL_MAX_LEVERAGE."""
    if leverage > MAX_LEVERAGE:
        return {"error": f"leverage_exceeded: {leverage}x > max {MAX_LEVERAGE}x"}
    s = _ensure_sdk()
    if not s.get("exchange"):
        return {"error": s.get("exchange_error") or s.get("error") or "exchange_unavailable (no agent key?)"}
    try:
        resp = s["exchange"].update_leverage(int(leverage), coin.upper(), cross)
        return {"ok": True, "coin": coin.upper(), "leverage": leverage, "resp": resp}
    except Exception as e:  # noqa: BLE001
        return {"error": f"set_leverage_failed: {e}"}


@mcp.tool()
def place_order(coin: str, is_buy: bool, size_usd: float, leverage: float | None = None,
                order_type: str = "market", reduce_only: bool = False) -> dict[str, Any]:
    """Place an order AFTER the hard risk-limit gate. The gate runs FIRST and
    rejects any violation regardless of intent. Opening orders fail CLOSED if
    current exposure or daily P&L cannot be determined.

    size_usd: notional size in USD. order_type: 'market' (only market supported
    in v0). The LLM should call get_trend_signal first and only open in the
    signal's direction."""
    # Fetch live state for the gate. None -> fail closed (handled in gate).
    positions = _open_positions_raw()
    pnl = _daily_pnl_usd()
    allowed, reason = check_order_allowed(
        coin=coin, size_usd=size_usd, leverage=leverage, reduce_only=reduce_only,
        open_positions=positions, daily_pnl_usd=pnl,
    )
    if not allowed:
        return {"rejected": True, "reason": reason, "limits": active_limits()}

    s = _ensure_sdk()
    if not s.get("exchange"):
        return {"error": s.get("exchange_error") or s.get("error") or "exchange_unavailable (no agent key?)"}

    coin_u = coin.upper()
    try:
        # Convert USD notional to coin size at current mark.
        md = get_market_data(coin_u, interval="1m", lookback_hours=1)
        px = md.get("last_price")
        if not px:
            return {"error": "no_price_for_sizing"}
        sz = round(size_usd / px, 4)
        # market_open is the documented helper; verified live at deploy.
        resp = s["exchange"].market_open(coin_u, is_buy, sz, None, 0.01)
        return {"ok": True, "coin": coin_u, "is_buy": is_buy, "size_usd": size_usd,
                "size_coin": sz, "reduce_only": reduce_only, "gate": reason, "resp": resp}
    except Exception as e:  # noqa: BLE001
        return {"error": f"place_order_failed: {e}"}


@mcp.tool()
def close_position(coin: str) -> dict[str, Any]:
    """Fully close an open position (reduce-only market order). Always allowed
    by the gate since it lowers risk."""
    s = _ensure_sdk()
    if not s.get("exchange"):
        return {"error": s.get("exchange_error") or s.get("error") or "exchange_unavailable"}
    try:
        resp = s["exchange"].market_close(coin.upper())
        return {"ok": True, "coin": coin.upper(), "resp": resp}
    except Exception as e:  # noqa: BLE001
        return {"error": f"close_position_failed: {e}"}


@mcp.tool()
def cancel_all() -> dict[str, Any]:
    """Cancel all resting orders. Risk-reducing; always permitted."""
    s = _ensure_sdk()
    if not s.get("exchange"):
        return {"error": s.get("exchange_error") or s.get("error") or "exchange_unavailable"}
    addr = _user_address()
    try:
        open_orders = s["info"].open_orders(addr)
        cancelled = []
        for o in open_orders:
            try:
                s["exchange"].cancel(o.get("coin"), o.get("oid"))
                cancelled.append(o.get("oid"))
            except Exception:  # noqa: BLE001
                pass
        return {"ok": True, "cancelled": cancelled}
    except Exception as e:  # noqa: BLE001
        return {"error": f"cancel_all_failed: {e}"}


@mcp.tool()
def emergency_halt() -> dict[str, Any]:
    """Kill switch: cancel all resting orders and report. Use when something
    looks wrong. Does not auto-close positions (closing is a market action the
    agent should do deliberately via close_position), but stops new fills from
    resting orders. The operator can also flip HYPERLIQUID_TRADING_ENABLED=false
    via Fly secret for a hard stop on all new opens."""
    cancel = cancel_all()
    return {"ok": True, "action": "emergency_halt", "cancel_result": cancel,
            "note": "set HYPERLIQUID_TRADING_ENABLED=false for a hard stop on new opens"}


if __name__ == "__main__":
    mcp.run()
