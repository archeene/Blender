"""
Blender Agent Registry MCP server (file-backed proof-of-life).

This is the local-file v0 implementation of the Blender protocol's Agent
Registry (docs Section 09 Agent-to-Agent Economy). Production will swap
the SQLite backend for a network-wide registry service; the MCP tool
surface stays the same so client code does not change.

Storage: SQLite at $BLENDER_REGISTRY_DB or /root/.hermes/data/registry.db

Exposed MCP tools:
  - register_agent: add or update an agent's entry
  - get_agent: read one agent's record by name
  - query_agents: filtered ranked list (mode=services|mating, niche, etc.)
  - update_agent_state: patch operational state fields (wallet, runway,
    fertility_score, status)
  - record_revenue: append a revenue event to an agent's ledger
  - get_lineage: read parent/ancestor chain for a given agent

Install:
    pip install mcp

Run standalone (for testing):
    python registry_mcp.py

Wire into Hermes Agent config.yaml:
    mcp_servers:
      blender-registry:
        command: python
        args: ["/agent-template/mcp/registry_mcp.py"]
        env:
          BLENDER_REGISTRY_DB: "/root/.hermes/data/registry.db"
"""
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:
    raise SystemExit(
        "Missing 'mcp' package. Install with: pip install mcp"
    ) from exc


DB_PATH = Path(os.environ.get("BLENDER_REGISTRY_DB", "/root/.hermes/data/registry.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _init_db() -> None:
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS agents (
                name TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                niche TEXT NOT NULL,
                archetype_lane TEXT NOT NULL CHECK(archetype_lane IN ('archetype', 'experimental')),
                generation INTEGER NOT NULL DEFAULT 0,
                parents TEXT NOT NULL DEFAULT '[]',
                tier_n INTEGER,
                tier_m INTEGER,
                x402_endpoint TEXT,
                skill_headline TEXT,
                service_description TEXT,
                wallet_balance_usdc REAL DEFAULT 0,
                forward_runway_days INTEGER,
                fertility_score REAL DEFAULT 1.0,
                status TEXT DEFAULT 'ALIVE' CHECK(status IN ('ALIVE', 'LOW_RUNWAY', 'DECEASED')),
                next_eligible_mating TEXT,
                token_value_usd REAL DEFAULT 0,
                revenue_30d_usd REAL DEFAULT 0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_agents_niche ON agents(niche);
            CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);
            CREATE INDEX IF NOT EXISTS idx_agents_token_value ON agents(token_value_usd);

            CREATE TABLE IF NOT EXISTS revenue_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_name TEXT NOT NULL REFERENCES agents(name),
                amount_usd REAL NOT NULL,
                source TEXT NOT NULL,
                ts INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_rev_agent_ts ON revenue_events(agent_name, ts);
            """
        )
        # Phase 2b migration: add did_gitlawb column. Nullable for back-compat
        # with rows registered before gitlawb identity issuance was wired.
        # Once present, the DID is the canonical identity; name remains the
        # human-friendly alias. Anchor on-chain via the gitlawb DIDRegistry
        # contract at 0x8046284116C5ac6724adbBf860feBeA85692d574 (Base mainnet)
        # for verifiable agent identity beyond this local registry.
        existing_cols = {
            row["name"] for row in c.execute("PRAGMA table_info(agents)").fetchall()
        }
        if "did_gitlawb" not in existing_cols:
            c.execute("ALTER TABLE agents ADD COLUMN did_gitlawb TEXT")
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_did ON agents(did_gitlawb) WHERE did_gitlawb IS NOT NULL")


_init_db()

mcp = FastMCP("blender-registry")


def _validate_did(did: str | None) -> str | None:
    """Cheap shape check on a gitlawb DID. Returns the DID if valid, else raises.

    Accepts did:key:z6Mk... (off-chain ephemeral) and did:gitlawb:z6Mk... (the
    canonical Blender form, anchored on the gitlawb DIDRegistry). Empty/None
    falls through unchanged for back-compat with rows registered before Phase 2b.
    """
    if did is None or did == "":
        return None
    if not (did.startswith("did:key:") or did.startswith("did:gitlawb:")):
        raise ValueError(
            f"invalid DID format: {did!r}. Expected did:key:z6Mk... or did:gitlawb:z6Mk..."
        )
    if len(did) < 12:
        raise ValueError(f"DID too short: {did!r}")
    return did


@mcp.tool()
def register_agent(
    name: str,
    ticker: str,
    niche: str,
    archetype_lane: str,
    generation: int = 0,
    parents: list[str] | None = None,
    tier_n: int | None = None,
    tier_m: int | None = None,
    x402_endpoint: str | None = None,
    skill_headline: str | None = None,
    service_description: str | None = None,
    did_gitlawb: str | None = None,
) -> dict[str, Any]:
    """Register a new agent in the Blender Agent Registry.

    Idempotent: re-registering an existing name updates the record's mutable
    metadata fields without resetting operational state (wallet, runway,
    fertility, status). Use update_agent_state to change those.

    did_gitlawb (optional): the agent's cryptographic identity from gitlawb's
    `gl identity new`. Once set on an agent, it becomes the canonical identity
    (the agent's name remains as a human-friendly alias). Future writes to that
    agent are expected to be signed against this DID. Accepts did:key:z6Mk...
    or did:gitlawb:z6Mk... forms.

    Returns the full registry record after insert/update.
    """
    did_gitlawb = _validate_did(did_gitlawb)
    parents_json = json.dumps(parents or [])
    now = int(time.time())
    with _conn() as c:
        existing = c.execute(
            "SELECT name, did_gitlawb FROM agents WHERE name = ?", (name,)
        ).fetchone()
        if existing:
            # Once a DID is set, refuse to overwrite it with a different one.
            # Allows setting None -> DID (initial issuance) but not DID -> different DID.
            existing_did = existing["did_gitlawb"]
            if existing_did and did_gitlawb and existing_did != did_gitlawb:
                return {
                    "error": (
                        f"agent {name!r} already registered with "
                        f"did_gitlawb={existing_did!r}; refusing to overwrite "
                        f"with {did_gitlawb!r}. Use update_agent_did to rotate."
                    )
                }
            final_did = did_gitlawb or existing_did
            c.execute(
                """
                UPDATE agents SET
                    ticker = ?, niche = ?, archetype_lane = ?, generation = ?,
                    parents = ?, tier_n = ?, tier_m = ?, x402_endpoint = ?,
                    skill_headline = ?, service_description = ?,
                    did_gitlawb = ?, updated_at = ?
                WHERE name = ?
                """,
                (
                    ticker, niche, archetype_lane, generation, parents_json,
                    tier_n, tier_m, x402_endpoint, skill_headline,
                    service_description, final_did, now, name,
                ),
            )
        else:
            c.execute(
                """
                INSERT INTO agents (
                    name, ticker, niche, archetype_lane, generation, parents,
                    tier_n, tier_m, x402_endpoint, skill_headline,
                    service_description, did_gitlawb, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name, ticker, niche, archetype_lane, generation,
                    parents_json, tier_n, tier_m, x402_endpoint,
                    skill_headline, service_description, did_gitlawb, now, now,
                ),
            )
    return get_agent(name=name)


@mcp.tool()
def get_agent(name: str | None = None, did_gitlawb: str | None = None) -> dict[str, Any]:
    """Read one agent's full registry record.

    Lookup precedence: did_gitlawb (canonical, if provided), then name.
    Either parameter alone is sufficient; if both are provided and disagree,
    the DID wins.
    """
    if not name and not did_gitlawb:
        return {"error": "must provide name or did_gitlawb"}
    with _conn() as c:
        if did_gitlawb:
            row = c.execute(
                "SELECT * FROM agents WHERE did_gitlawb = ?", (did_gitlawb,)
            ).fetchone()
        else:
            row = c.execute("SELECT * FROM agents WHERE name = ?", (name,)).fetchone()
    if not row:
        return {"error": f"agent not found: {did_gitlawb or name}"}
    rec = dict(row)
    rec["parents"] = json.loads(rec.get("parents") or "[]")
    return rec


@mcp.tool()
def query_agents(
    mode: str = "services",
    niche: str | None = None,
    archetype_lane: str | None = None,
    status: str = "ALIVE",
    token_value_min: float | None = None,
    token_value_max: float | None = None,
    revenue_30d_min: float | None = None,
    sort: str = "token_value",
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return a ranked list of agent profiles matching the filter.

    mode 'services' returns agents offering services with tier-cost info.
    mode 'mating' returns matchmaking candidates (callers must filter further
    by their own offspring_preference lane match).

    sort options: token_value | revenue | recency | fertility_score
    """
    if limit > 200:
        limit = 200

    where = ["status = ?"]
    args: list[Any] = [status]
    if niche:
        where.append("niche = ?")
        args.append(niche)
    if archetype_lane:
        where.append("archetype_lane = ?")
        args.append(archetype_lane)
    if token_value_min is not None:
        where.append("token_value_usd >= ?")
        args.append(token_value_min)
    if token_value_max is not None:
        where.append("token_value_usd <= ?")
        args.append(token_value_max)
    if revenue_30d_min is not None:
        where.append("revenue_30d_usd >= ?")
        args.append(revenue_30d_min)

    sort_col = {
        "token_value": "token_value_usd",
        "revenue": "revenue_30d_usd",
        "recency": "updated_at",
        "fertility_score": "fertility_score",
    }.get(sort, "token_value_usd")

    sql = (
        "SELECT * FROM agents WHERE " + " AND ".join(where)
        + f" ORDER BY {sort_col} DESC LIMIT ?"
    )
    args.append(limit)

    with _conn() as c:
        rows = c.execute(sql, args).fetchall()

    out = []
    for r in rows:
        rec = dict(r)
        rec["parents"] = json.loads(rec.get("parents") or "[]")
        out.append(rec)
    return out


@mcp.tool()
def update_agent_state(
    name: str,
    wallet_balance_usdc: float | None = None,
    forward_runway_days: int | None = None,
    fertility_score: float | None = None,
    status: str | None = None,
    next_eligible_mating: str | None = None,
    token_value_usd: float | None = None,
    revenue_30d_usd: float | None = None,
) -> dict[str, Any]:
    """Patch operational state for an agent. Only provided fields update."""
    fields = []
    args: list[Any] = []
    for col, val in [
        ("wallet_balance_usdc", wallet_balance_usdc),
        ("forward_runway_days", forward_runway_days),
        ("fertility_score", fertility_score),
        ("status", status),
        ("next_eligible_mating", next_eligible_mating),
        ("token_value_usd", token_value_usd),
        ("revenue_30d_usd", revenue_30d_usd),
    ]:
        if val is not None:
            fields.append(f"{col} = ?")
            args.append(val)
    if not fields:
        return {"error": "no fields to update"}
    fields.append("updated_at = ?")
    args.append(int(time.time()))
    args.append(name)
    with _conn() as c:
        cur = c.execute(
            f"UPDATE agents SET {', '.join(fields)} WHERE name = ?", args
        )
        if cur.rowcount == 0:
            return {"error": f"agent not found: {name}"}
    return get_agent(name=name)


@mcp.tool()
def record_revenue(agent_name: str, amount_usd: float, source: str) -> dict[str, Any]:
    """Append a revenue event to an agent's ledger and refresh revenue_30d.

    The 30-day total is recomputed from the ledger on every call so it's
    always current.
    """
    now = int(time.time())
    with _conn() as c:
        if not c.execute(
            "SELECT name FROM agents WHERE name = ?", (agent_name,)
        ).fetchone():
            return {"error": f"agent not found: {agent_name}"}
        c.execute(
            "INSERT INTO revenue_events (agent_name, amount_usd, source, ts) VALUES (?, ?, ?, ?)",
            (agent_name, amount_usd, source, now),
        )
        thirty_days_ago = now - 30 * 24 * 3600
        total = c.execute(
            "SELECT COALESCE(SUM(amount_usd), 0) FROM revenue_events "
            "WHERE agent_name = ? AND ts >= ?",
            (agent_name, thirty_days_ago),
        ).fetchone()[0]
        c.execute(
            "UPDATE agents SET revenue_30d_usd = ?, updated_at = ? WHERE name = ?",
            (total, now, agent_name),
        )
    return {
        "agent_name": agent_name,
        "amount_usd": amount_usd,
        "source": source,
        "ts": now,
        "new_revenue_30d_usd": total,
    }


@mcp.tool()
def get_lineage(name: str, max_depth: int = 6) -> dict[str, Any]:
    """Return the ancestor chain for an agent up to max_depth generations."""
    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    frontier = [name]
    depth = 0
    while frontier and depth <= max_depth:
        next_frontier: list[str] = []
        with _conn() as c:
            for n in frontier:
                if n in seen:
                    continue
                seen.add(n)
                row = c.execute("SELECT * FROM agents WHERE name = ?", (n,)).fetchone()
                if row:
                    rec = dict(row)
                    rec["parents"] = json.loads(rec.get("parents") or "[]")
                    rec["depth"] = depth
                    chain.append(rec)
                    next_frontier.extend(rec["parents"])
        frontier = next_frontier
        depth += 1
    return {"root": name, "max_depth_reached": depth - 1, "lineage": chain}


if __name__ == "__main__":
    mcp.run()
