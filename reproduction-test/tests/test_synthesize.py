"""Smoke tests for synthesize_offspring.py.

Run:
    python reproduction-test/tests/test_synthesize.py

Exit status:
    0 = all pass
    1 = at least one assertion failed
    2 = test harness / import error

No third-party deps. Stdlib + the module under test, which itself is stdlib only.
"""
import sys
from pathlib import Path

# Make the synthesis module importable without packaging.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "synthesis"))

try:
    import synthesize_offspring as so  # noqa: E402
except Exception as e:  # pragma: no cover
    print(f"[test_synthesize] ERROR importing synthesize_offspring: {e}", file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------

def _base_manifest():
    """A complete, valid manifest used as the starting point for each test."""
    return {
        "offspring_name": "yield-aggregator",
        "offspring_ticker": "YAGG",
        "locked_niche": "defi_auto_trader",
        "soul_md": (
            "LAYER 0\n\n"
            "Maximize the value of $TOKEN_SELF, the Clawnch token launched at my birth. "
            "Every action I take, every cron I run, every dollar I spend, every mating I "
            "initiate, every project I queue must serve this single goal.\n\n"
            "LAYER 1\n\nSomething synthesized.\n\nLAYER 2\n\n(empty)\n"
        ),
        "memory_md": "voice\nbrand vocab\npatterns\nlessons (empty)\n",
        "user_md": (
            "# USER\n\n"
            "**Name**: yield-aggregator\n"
            "**Ticker**: $YAGG\n"
            "**Niche**: defi_auto_trader\n"
        ),
        "cron_jobs": [
            {"name": "monitoring_scan", "tier": 1, "schedule": "*/15 * * * *", "prompt": "scan"},
            {"name": "nightly_triage", "tier": 1, "schedule": "0 2 * * *", "prompt": "triage"},
            {"name": "weekly_planning", "tier": 1, "schedule": "0 9 * * 1", "prompt": "plan"},
            {"name": "weekly_reflection", "tier": 1, "schedule": "0 17 * * 5", "prompt": "reflect"},
            {"name": "protocol_sync", "tier": 1, "schedule": "0 * * * *", "prompt": "sync"},
            {"name": "hourly_action", "tier": 2, "schedule": "30 * * * *", "prompt": "act"},
        ],
        "synthesis_notes": "Inherited X from A and Y from B.",
    }


# ---------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------

_results = []


def _t(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    _results.append((status, name, detail))
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail and not cond else ""))


def run_tests():
    print("== validate_manifest ==")
    m = _base_manifest()
    issues = so.validate_manifest(m)
    _t("base manifest passes", issues == [], detail=str(issues))

    m = _base_manifest()
    m["locked_niche"] = "not_a_real_niche"
    issues = so.validate_manifest(m)
    _t("invalid niche flagged", any("locked_niche" in i for i in issues), detail=str(issues))

    m = _base_manifest()
    m["offspring_name"] = "Bad_Name_Caps"
    issues = so.validate_manifest(m)
    _t("invalid name (caps+underscore) flagged", any("offspring_name" in i for i in issues), detail=str(issues))

    m = _base_manifest()
    m["offspring_ticker"] = "lowercase"
    issues = so.validate_manifest(m)
    _t("lowercase ticker flagged", any("offspring_ticker" in i for i in issues), detail=str(issues))

    m = _base_manifest()
    m["offspring_ticker"] = "TOOLONG"
    issues = so.validate_manifest(m)
    _t("7-char ticker flagged", any("offspring_ticker" in i for i in issues), detail=str(issues))

    m = _base_manifest()
    m["soul_md"] = "no canonical sentence in here"
    issues = so.validate_manifest(m)
    _t("missing LAYER 0 flagged", any("LAYER 0" in i for i in issues), detail=str(issues))

    m = _base_manifest()
    m["user_md"] = "Name: foo\nTicker: BAR\nNiche: baz\n"  # plain colons, not bolded
    issues = so.validate_manifest(m)
    _t("user_md without bolded headers flagged", any("user_md missing required header" in i for i in issues), detail=str(issues))

    m = _base_manifest()
    m["cron_jobs"][0].pop("schedule")
    issues = so.validate_manifest(m)
    _t("cron missing schedule flagged", any("missing field `schedule`" in i for i in issues), detail=str(issues))

    m = _base_manifest()
    m["cron_jobs"][0]["tier"] = 9
    issues = so.validate_manifest(m)
    _t("cron invalid tier flagged", any("tier must be" in i for i in issues), detail=str(issues))

    print("\n== enforce_tier1_hygiene ==")
    m = _base_manifest()
    m["cron_jobs"] = [c for c in m["cron_jobs"] if c["name"] != "protocol_sync"]
    added = so.enforce_tier1_hygiene(m)
    _t("missing protocol_sync auto-merged", added == ["protocol_sync"], detail=f"added={added}")
    issues = so.validate_manifest(m)
    _t("validation clean after auto-merge", not any("Tier-1" in i for i in issues), detail=str(issues))

    m = _base_manifest()
    m["cron_jobs"] = []
    added = so.enforce_tier1_hygiene(m)
    _t("all 5 tier-1 crons auto-merged when none present", len(added) == 5 and set(added) == so.TIER1_REQUIRED_NAMES, detail=f"added={added}")

    m = _base_manifest()
    added = so.enforce_tier1_hygiene(m)
    _t("complete manifest no auto-merge", added == [], detail=f"added={added}")

    print("\n== attach_parent_dids + compute_inheritance_hash ==")
    m = _base_manifest()
    so.attach_parent_dids(m, "did:gitlawb:z6MkAAAA000000000000000000000000000000000000000", "did:gitlawb:z6MkBBBB000000000000000000000000000000000000000")
    _t("both parent DIDs stamped", m["parent_dids"]["parent_a"].startswith("did:gitlawb:") and m["parent_dids"]["parent_b"].startswith("did:gitlawb:"))
    _t("inheritance_hash is 64-char hex", len(m["inheritance_hash"]) == 64 and all(c in "0123456789abcdef" for c in m["inheritance_hash"]))
    _t("parent_signatures slots empty", m["parent_signatures"] == {"parent_a": None, "parent_b": None})

    # determinism
    h1 = so.compute_inheritance_hash({"soul_md": "x", "memory_md": "y", "user_md": "z", "cron_jobs": [{"name": "a"}]})
    h2 = so.compute_inheritance_hash({"soul_md": "x", "memory_md": "y", "user_md": "z", "cron_jobs": [{"name": "a"}]})
    _t("hash deterministic", h1 == h2)
    h3 = so.compute_inheritance_hash({"soul_md": "x", "memory_md": "y", "user_md": "z", "cron_jobs": [{"name": "b"}]})
    _t("hash changes on cron edit", h1 != h3)
    h4 = so.compute_inheritance_hash({"soul_md": "X", "memory_md": "y", "user_md": "z", "cron_jobs": [{"name": "a"}]})
    _t("hash changes on soul edit", h1 != h4)

    print("\n== parse_offspring ==")
    raw = '{"offspring_name":"x","offspring_ticker":"X","locked_niche":"experimental","soul_md":"a","memory_md":"b","user_md":"c","cron_jobs":[],"synthesis_notes":"n"}'
    parsed = so.parse_offspring(raw)
    _t("clean JSON parses", parsed["offspring_name"] == "x")

    # tolerant of leading code fence
    raw_fenced = "```json\n" + raw + "\n```"
    parsed = so.parse_offspring(raw_fenced)
    _t("```-fenced JSON parses", parsed["offspring_name"] == "x")

    # tolerant of prose-then-JSON (LLM commentary before payload)
    raw_messy = "Here is the manifest you requested:\n\n" + raw + "\n\nLet me know if you need anything else."
    parsed = so.parse_offspring(raw_messy)
    _t("messy LLM output (commentary+JSON+commentary) parses", parsed["offspring_name"] == "x")


def main():
    print("Running synthesize_offspring smoke tests...\n")
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
