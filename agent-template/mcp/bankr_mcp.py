"""
Bankr MCP server: wraps the Bankr agent-banking API for Hermes Agent.

Bankr (https://bankr.bot) is the financial infrastructure layer for AI agents
on Base: wallet creation, x402 endpoint hosting, USDC settlement, agent
discovery. This MCP exposes the subset of the Bankr API a Blender offspring
needs to operate.

Required env:
  BANKR_API_KEY    Your Bankr API key (already configured in the existing
                   blender-agent Fly app's secrets per the May 2026 deploy)

Tools exposed:
  - get_wallet_balance(): read the agent's current USDC + WETH balance on Base
  - list_x402_endpoints(): enumerate paid endpoints deployed by this wallet
  - get_endpoint_stats(slug): per-endpoint call count + revenue + recent callers
  - claim_clawnch_fees(token_address): claim accumulated WETH trading-fee share
                                       from a Clawnch token launched by this agent
  - send_usdc(to_address, amount): send USDC on Base (requires explicit value
                                   cap from agent's own policy; not unbounded)

This is the minimum viable surface. Bankr's full API also covers x402 deploy
(handled via `bankr x402 deploy` CLI, exposed as a shell tool in Hermes; not
duplicated here), wallet creation (one-time, done at agent birth, not a
runtime operation), and agent discovery (handled by the blender-registry
MCP at the Blender-protocol level).

Stdlib only (urllib.request, json, os). MCP SDK required (pip install mcp).
"""
import json
import os
import urllib.error
import urllib.request
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:
    raise SystemExit(
        "Missing 'mcp' package. Install with: pip install mcp"
    ) from exc


BANKR_BASE = os.environ.get("BANKR_API_BASE", "https://api.bankr.bot/v1")
API_KEY = os.environ.get("BANKR_API_KEY", "")

mcp = FastMCP("bankr")


def _request(
    method: str,
    path: str,
    body: dict | None = None,
    params: dict | None = None,
) -> dict[str, Any]:
    """Low-level HTTP wrapper. Returns parsed JSON or {'error': ...} dict."""
    if not API_KEY:
        return {"error": "BANKR_API_KEY env var not set; cannot call Bankr API."}

    url = f"{BANKR_BASE.rstrip('/')}/{path.lstrip('/')}"
    if params:
        from urllib.parse import urlencode
        url = f"{url}?{urlencode({k: v for k, v in params.items() if v is not None})}"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {"ok": True}
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return {
            "error": f"HTTP {e.code} from Bankr",
            "code": e.code,
            "url": url,
            "body": err_body[:1000],
        }
    except urllib.error.URLError as e:
        return {"error": f"URL error: {e}", "url": url}
    except json.JSONDecodeError as e:
        return {"error": f"non-JSON response: {e}", "url": url}


@mcp.tool()
def get_wallet_balance() -> dict[str, Any]:
    """Return the agent's current Bankr-managed wallet balance on Base.

    Returns a dict with at least:
      - address: the wallet address (0x...)
      - usdc: USDC balance in dollars (float)
      - weth: WETH balance in ether (float)
      - eth: native ETH balance (float, for gas)
      - updated_at: ISO timestamp
    """
    return _request("GET", "/wallet/balance")


@mcp.tool()
def list_x402_endpoints() -> dict[str, Any]:
    """List all x402-Cloud paid endpoints deployed by this agent's wallet.

    Each entry includes slug, full URL, price per call in USDC, deployment
    date, current handler version, and lifetime call count.
    """
    return _request("GET", "/x402/endpoints")


@mcp.tool()
def get_endpoint_stats(slug: str, window_hours: int = 24) -> dict[str, Any]:
    """Per-endpoint metrics for an x402-Cloud endpoint owned by this agent.

    slug: the endpoint's path slug (e.g. 'yield-recommendations')
    window_hours: lookback window for the stats. Default 24h. Max 720 (30d).

    Returns: call count, total USDC revenue, unique callers, error rate,
    median latency, top 10 caller wallets in the window.
    """
    return _request(
        "GET",
        f"/x402/endpoints/{slug}/stats",
        params={"window_hours": min(max(window_hours, 1), 720)},
    )


@mcp.tool()
def claim_clawnch_fees(token_address: str) -> dict[str, Any]:
    """Claim accumulated WETH trading-fee share from a Clawnch token this
    agent launched. Returns transaction hash + amount claimed.

    token_address: the Clawnch token contract address on Base (0x...)

    Per the Clawnch agent-autonomy loop, fee claims accumulate continuously
    as the token trades; calling this materializes them into the agent's
    Bankr wallet as WETH.
    """
    return _request(
        "POST",
        "/clawnch/claim",
        body={"token_address": token_address},
    )


@mcp.tool()
def send_usdc(to_address: str, amount_usd: float, memo: str = "") -> dict[str, Any]:
    """Send USDC on Base from the agent's Bankr wallet.

    to_address: destination 0x... address
    amount_usd: amount in dollars (float). The agent should enforce its
                own per-transaction and per-day caps in the calling cron
                or skill; this MCP does NOT impose a cap.
    memo: optional human-readable memo (logged but not on-chain)

    Returns: transaction hash, new wallet balance, gas paid.
    """
    if amount_usd <= 0:
        return {"error": "amount_usd must be positive"}
    return _request(
        "POST",
        "/wallet/send",
        body={
            "to": to_address,
            "asset": "USDC",
            "amount_usd": amount_usd,
            "memo": memo,
        },
    )


@mcp.tool()
def list_recent_payments(limit: int = 25) -> dict[str, Any]:
    """List the most recent USDC payments received by this agent's wallet.

    Each entry: from_address, amount_usd, asset, source_endpoint (if from an
    x402 call), ts. Used by the monitoring_scan cron to detect significant
    inbound payments above the agent's threshold.
    """
    return _request(
        "GET",
        "/wallet/payments",
        params={"limit": min(max(limit, 1), 100)},
    )


if __name__ == "__main__":
    mcp.run()
