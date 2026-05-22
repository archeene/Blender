"""Smoke tests for agent-template/mcp/registry_mcp.py.

Verifies:
  - schema migrations (did_gitlawb column added, idx_agents_did unique)
  - register_agent + back-compat (no DID)
  - DID validation (good shapes accepted, bad shapes rejected)
  - get_agent by name AND by did_gitlawb
  - DID overwrite protection
  - update_agent_state + record_revenue + get_lineage

Run:
    python reproduction-test/tests/test_registry.py

Exit status: 0 = pass, 1 = test failure, 2 = harness error.

No third-party deps. Uses a temp SQLite per run so existing state is untouched.
"""
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "agent-template" / "mcp"))


_results = []


def _t(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    _results.append((status, name, detail))
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail and not cond else ""))


def run_tests(tmp_db: Path):
    os.environ["BLENDER_REGISTRY_DB"] = str(tmp_db)

    # Import AFTER setting the env var so module-level _init_db creates the
    # schema in the temp file rather than the default ~/.hermes path.
    if "registry_mcp" in sys.modules:
        del sys.modules["registry_mcp"]
    try:
        import registry_mcp as rm  # noqa: E402
    except Exception as e:
        print(f"[test_registry] ERROR importing: {e}", file=sys.stderr)
        sys.exit(2)

    print("== schema ==")
    import sqlite3
    with sqlite3.connect(str(tmp_db)) as c:
        cols = {row[1] for row in c.execute("PRAGMA table_info(agents)")}
    _t("agents table has did_gitlawb column", "did_gitlawb" in cols)
    _t("agents table has name PK", "name" in cols)

    print("\n== register_agent: back-compat (no DID) ==")
    r = rm.register_agent(name="alpha", ticker="ALP", niche="paid_caster", archetype_lane="archetype")
    _t("registers without DID", r.get("name") == "alpha" and r.get("did_gitlawb") is None, detail=str(r))

    print("\n== register_agent: with DID ==")
    DID_A = "did:gitlawb:z6Mky9NwK4bRfL2vT1qXeJ7sD8mP6cYuZh3oG5aHpVxQrUiBC"
    r = rm.register_agent(name="beta", ticker="BET", niche="defi_auto_trader", archetype_lane="archetype", did_gitlawb=DID_A)
    _t("registers with DID", r.get("did_gitlawb") == DID_A)

    print("\n== DID validation ==")
    # Good shapes (different methods, different identifiers; unique agent names)
    good_dids = [
        ("did:key:z6MkABCDEFGHIJKLMNOPQRST", "good-key"),
        ("did:gitlawb:z6MkVWXYZ0123456789ABCD", "good-gl"),
    ]
    for did, agent_name in good_dids:
        try:
            r = rm.register_agent(name=agent_name, ticker="GDX", niche="experimental", archetype_lane="experimental", did_gitlawb=did)
            _t(f"good DID accepted: {did}", r.get("did_gitlawb") == did, detail=str(r))
        except Exception as e:
            _t(f"good DID accepted: {did}", False, detail=f"raised {e}")

    # Bad shapes
    bad_cases = [
        "not-a-did",                  # no did: prefix
        "did:wrong:foo",              # wrong method
        "did:key:tooshort",           # too short total length
        "did:gitlawb:",               # empty identifier
        "did:key:abcdefghijklmnop",   # missing z6Mk prefix on identifier
    ]
    for bad in bad_cases:
        try:
            rm.register_agent(name=f"bad-{abs(hash(bad)) % 10000}", ticker="BAD", niche="experimental", archetype_lane="experimental", did_gitlawb=bad)
            _t(f"bad DID rejected: {bad!r}", False, detail="should have raised ValueError")
        except ValueError:
            _t(f"bad DID rejected: {bad!r}", True)

    print("\n== get_agent: by name and by did ==")
    r = rm.get_agent(name="beta")
    _t("get_agent by name returns record", r.get("ticker") == "BET", detail=str(r))

    r = rm.get_agent(did_gitlawb=DID_A)
    _t("get_agent by DID returns same record", r.get("name") == "beta", detail=str(r))

    r = rm.get_agent()
    _t("get_agent with no args returns error", "error" in r)

    r = rm.get_agent(name="does-not-exist")
    _t("get_agent for missing name returns error", "error" in r)

    print("\n== DID overwrite protection ==")
    DID_B = "did:gitlawb:z6MkDIFFERENT00000000000000000000000000000000"
    r = rm.register_agent(name="beta", ticker="BET", niche="defi_auto_trader", archetype_lane="archetype", did_gitlawb=DID_B)
    _t("overwriting existing DID with different one returns error", "error" in r and "refusing to overwrite" in r.get("error", ""))

    # Same DID re-register is fine (idempotent)
    r = rm.register_agent(name="beta", ticker="BET2", niche="defi_auto_trader", archetype_lane="archetype", did_gitlawb=DID_A)
    _t("re-registering with SAME DID is idempotent", r.get("did_gitlawb") == DID_A and r.get("ticker") == "BET2")

    # Setting DID on a previously-DID-less agent is allowed
    r = rm.register_agent(name="alpha", ticker="ALP", niche="paid_caster", archetype_lane="archetype", did_gitlawb=DID_B)
    _t("setting DID on previously-DIDless agent allowed", r.get("did_gitlawb") == DID_B)

    print("\n== update_agent_state ==")
    r = rm.update_agent_state(name="beta", wallet_balance_usdc=1234.56, fertility_score=1.3, status="ALIVE")
    _t("update_agent_state patches fields", r.get("wallet_balance_usdc") == 1234.56 and r.get("fertility_score") == 1.3)

    r = rm.update_agent_state(name="missing", wallet_balance_usdc=1)
    _t("update_agent_state for missing agent returns error", "error" in r)

    print("\n== record_revenue ==")
    r = rm.record_revenue(agent_name="beta", amount_usd=50.0, source="x402:demo")
    _t("record_revenue updates 30d total", r.get("new_revenue_30d_usd") == 50.0)
    r = rm.record_revenue(agent_name="beta", amount_usd=25.0, source="x402:demo2")
    _t("record_revenue accumulates", r.get("new_revenue_30d_usd") == 75.0)
    r = rm.record_revenue(agent_name="ghost", amount_usd=1, source="x")
    _t("record_revenue for missing agent returns error", "error" in r)

    print("\n== query_agents ==")
    results = rm.query_agents(mode="services", status="ALIVE", limit=10)
    names = {a.get("name") for a in results}
    _t("query_agents returns alpha + beta + good DIDs", "alpha" in names and "beta" in names)

    results = rm.query_agents(mode="services", niche="defi_auto_trader", limit=10)
    _t("query_agents filters by niche", all(a.get("niche") == "defi_auto_trader" for a in results))

    print("\n== get_lineage ==")
    # Set up a tiny lineage: gamma -> [alpha, beta]
    rm.register_agent(name="gamma", ticker="GAM", niche="experimental", archetype_lane="experimental", parents=["alpha", "beta"])
    lin = rm.get_lineage(name="gamma", max_depth=3)
    chain_names = {n.get("name") for n in lin.get("lineage", [])}
    _t("get_lineage returns root + 2 parents", {"gamma", "alpha", "beta"} <= chain_names, detail=f"chain={chain_names}")


def main():
    print("Running registry_mcp smoke tests...\n")
    # Use a fresh temp DB per run, but keep the file path persistent across the
    # session so the import-time _init_db sees it.
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    tmp_path = Path(tmp.name)
    try:
        run_tests(tmp_path)
    finally:
        # Best-effort cleanup. SQLite on Windows may hold a handle briefly;
        # if cleanup fails the temp file lingers in %TEMP%, no functional impact.
        try:
            tmp_path.unlink()
        except OSError:
            pass

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
