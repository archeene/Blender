"""
Synthesis Service prototype for the Blender Protocol reproduction test.

Takes two parent agent directories. Reads each parent's inheritance bundle
(SOUL.md, MEMORY.md, USER.md, cron_jobs.json) and composes a Mating Manifest
for their offspring via a single LLM call. Writes the offspring's inheritance
files to a target directory.

Usage:
    export OPENROUTER_API_KEY=sk-or-v1-...
    python synthesize_offspring.py <parent_a_dir> <parent_b_dir> <offspring_out_dir>

Example:
    python synthesize_offspring.py \\
        ../parents/alphacaller \\
        ../parents/yieldrotator \\
        ../offspring/run_001

Cost: $0 on OpenRouter's free Hermes 3 405B tier (rate-limited; one synthesis
call uses ~6-10k tokens). Free tier is fine for testing; switch model for
production.

Stdlib only (urllib.request). No third-party deps. Runs on Python 3.10+.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
import urllib.request
import urllib.error


def read_parent(parent_dir: Path) -> dict:
    """Read all 4 inheritance files from a parent's directory."""
    required = ["SOUL.md", "MEMORY.md", "USER.md", "cron_jobs.json"]
    missing = [f for f in required if not (parent_dir / f).exists()]
    if missing:
        raise FileNotFoundError(
            f"Parent dir {parent_dir} missing required files: {missing}"
        )
    return {
        "name": parent_dir.name,
        "soul": (parent_dir / "SOUL.md").read_text(encoding="utf-8"),
        "memory": (parent_dir / "MEMORY.md").read_text(encoding="utf-8"),
        "user": (parent_dir / "USER.md").read_text(encoding="utf-8"),
        "crons": json.loads(
            (parent_dir / "cron_jobs.json").read_text(encoding="utf-8")
        ),
    }


SYNTHESIS_INSTRUCTIONS = """You are the Blender Protocol's Synthesis Service.

You are given two parent agents' complete inheritance bundles. Your job: produce a single offspring's Mating Manifest that inherits from both parents coherently per the protocol rules.

PROTOCOL RULES:

1. LAYER 0 of SOUL.md is IMMUTABLE and identical for every Blender offspring:
   "Maximize the value of $TOKEN_SELF, the Clawnch token launched at my birth.
   Every action I take, every cron I run, every dollar I spend, every mating I
   initiate, every project I queue must serve this single goal."

2. LAYER 1 of SOUL.md is freshly synthesized from both parents. Pick ONE locked niche for the offspring based on the parents' niche signals and the LLM-judged best fit. Voice rubric is blended niche-aware. Identity (name + ticker) is novel, not copied from either parent.

3. LAYER 2 of SOUL.md starts EMPTY; the offspring fills it over its lifetime.

4. Cron skeleton has three tiers:
   - Tier 1 hygiene (IMMUTABLE, same across all offspring): monitoring_scan (*/15 * * * *), nightly_triage (0 2 * * *), weekly_planning (0 9 * * 1), weekly_reflection (0 17 * * 5), protocol_sync (0 * * * *). All five MUST appear in cron_jobs with tier=1. The post-synthesis validator will reject and auto-merge any missing Tier-1 hygiene cron.
   - Tier 2 tunable: hourly_action, morning_briefing, weekly_content. Pick the parent's tuning that is CLOSER to the offspring's locked niche. weekly_content may be disabled only if the locked niche genuinely has no public-content output.
   - Tier 3 extensible: include the most niche-relevant custom crons from either parent, capped at 8 total. Drop crons that don't fit the offspring's niche.

5. MEMORY.md sections (voice rubric, brand vocabulary, customer language samples, patterns_that_work) blend both parents niche-aware. Lessons-from-this-quarter and open-questions start EMPTY for a newborn.

6. USER.md is the offspring's NEW self-model: new name, new ticker, new niche, parents are both source agents, operational state fields (wallet, runway, fertility_score) all blank/zero.

7. Output a synthesis_notes paragraph explaining what was inherited from each parent and why.

LOCKED NICHE must be one of (the 12 Tier-1 archetypes plus experimental):
  crypto_twitter_narrative_aggregator
  token_launcher
  wallet_banking_execution
  defi_auto_trader
  prediction_market_bettor
  autonomous_coding
  pay_per_call_x402_api
  a2a_service_marketplace
  smart_contract_audit
  nft_scanner
  onchain_casino
  revenue_backed_agent
  experimental

OUTPUT FORMAT (raw JSON only, no markdown fences, no commentary):

{
  "offspring_name": "<short kebab-case, ~10 chars max>",
  "offspring_ticker": "<3-6 uppercase chars>",
  "locked_niche": "<one of the 13 enum values above>",
  "soul_md": "<full SOUL.md content - markdown text including immutable LAYER 0, synthesized LAYER 1, empty LAYER 2, the cron skeleton tier doc, constraints section>",
  "memory_md": "<full MEMORY.md content - markdown text>",
  "user_md": "<full USER.md content - markdown text>",
  "cron_jobs": [
    {"name": "<cron name>", "tier": <1|2|3>, "tier_label": "<label>", "schedule": "<cron expr>", "prompt": "<full natural-language cron prompt>"}
  ],
  "synthesis_notes": "<paragraph explaining inheritance decisions>"
}"""


def compose_synthesis_prompt(parent_a: dict, parent_b: dict) -> str:
    return f"""{SYNTHESIS_INSTRUCTIONS}

==============================
PARENT A: {parent_a["name"]}
==============================

[SOUL.md]
{parent_a["soul"]}

[MEMORY.md]
{parent_a["memory"]}

[USER.md]
{parent_a["user"]}

[cron_jobs.json]
{json.dumps(parent_a["crons"], indent=2)}

==============================
PARENT B: {parent_b["name"]}
==============================

[SOUL.md]
{parent_b["soul"]}

[MEMORY.md]
{parent_b["memory"]}

[USER.md]
{parent_b["user"]}

[cron_jobs.json]
{json.dumps(parent_b["crons"], indent=2)}

==============================

Return the offspring's Mating Manifest as a single raw JSON object now.
"""


def call_llm(prompt: str, model: str, api_key: str, base_url: str) -> str:
    """Call an OpenAI-compatible chat-completions endpoint with the prompt."""
    url = base_url.rstrip("/") + "/chat/completions"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 12000,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://blenderai.link",
            "X-Title": "Blender Protocol Synthesis Test",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code} from {url}:\n{err_body}", file=sys.stderr)
        raise
    except urllib.error.URLError as e:
        print(f"URL error reaching {url}: {e}", file=sys.stderr)
        raise


def parse_offspring(raw: str) -> dict:
    """Parse the LLM's JSON output into a Mating Manifest dict. Tolerant of code-fence wrappers."""
    s = raw.strip()
    # Strip leading code fence if present
    if s.startswith("```"):
        first_newline = s.find("\n")
        if first_newline != -1:
            s = s[first_newline + 1 :]
        if s.endswith("```"):
            s = s.rsplit("```", 1)[0]
        s = s.strip()
    # Find the outermost JSON object boundaries
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(
            f"No JSON object found in LLM output. First 200 chars: {raw[:200]!r}"
        )
    obj_text = s[start : end + 1]
    try:
        return json.loads(obj_text)
    except json.JSONDecodeError as e:
        print(
            f"JSON parse failed at line {e.lineno} col {e.colno}: {e.msg}\n"
            f"Snippet around error: {obj_text[max(0, e.pos - 100): e.pos + 100]!r}",
            file=sys.stderr,
        )
        raise


REQUIRED_MANIFEST_FIELDS = [
    "offspring_name",
    "offspring_ticker",
    "locked_niche",
    "soul_md",
    "memory_md",
    "user_md",
    "cron_jobs",
    "synthesis_notes",
]

# Protocol-standard Tier-1 hygiene crons. Every Blender offspring MUST register
# all five at birth. The LLM is prompted to include them, but if it drops any
# (Hermes 4 70B dropped protocol_sync from yield-aggregator's manifest, 2026-05-19),
# the synthesizer auto-merges the missing ones from this canonical set rather
# than shipping an offspring that can't poll the bulletin board.
TIER1_HYGIENE_CRONS = [
    {
        "name": "monitoring_scan",
        "tier": 1,
        "tier_label": "hygiene",
        "schedule": "*/15 * * * *",
        "prompt": (
            "Scan current operational state every 15 minutes. Read system metrics, "
            "check for anomalies vs MEMORY.md thresholds, flag urgent items needing "
            "the next hourly_action. Output a single status line; if anything is "
            "urgent, queue it for hourly_action."
        ),
    },
    {
        "name": "nightly_triage",
        "tier": 1,
        "tier_label": "hygiene",
        "schedule": "0 2 * * *",
        "prompt": (
            "Triage the day. Review what fired, what worked, what didn't. Roll up "
            "revenue, drawdown, errors. Update operational state in USER.md."
        ),
    },
    {
        "name": "weekly_planning",
        "tier": 1,
        "tier_label": "hygiene",
        "schedule": "0 9 * * 1",
        "prompt": (
            "Pick top 3 backlog items for the week. Sequence them. Output the week "
            "plan as a project list."
        ),
    },
    {
        "name": "weekly_reflection",
        "tier": 1,
        "tier_label": "hygiene",
        "schedule": "0 17 * * 5",
        "prompt": (
            "End-of-week reflection. What lessons emerged? What patterns are "
            "working? Update MEMORY.md lessons section."
        ),
    },
    {
        "name": "protocol_sync",
        "tier": 1,
        "tier_label": "hygiene",
        "schedule": "0 * * * *",
        "prompt": (
            "Run the protocol_sync skill: fetch the Blender protocol bulletin "
            "board manifest, diff against processed_bulletins.json, apply "
            "machine_instructions for required/urgent bulletins within the safety "
            "allow-list, queue recommendations into the project backlog, log to "
            "Molt Book. Reject anything outside the allow-list and publish a "
            "needs_input post."
        ),
    },
]

TIER1_REQUIRED_NAMES = {c["name"] for c in TIER1_HYGIENE_CRONS}


def enforce_tier1_hygiene(manifest: dict) -> list[str]:
    """Auto-merge any missing Tier-1 hygiene crons from the canonical set.

    Returns the list of cron names that had to be auto-merged (empty list means
    the LLM produced everything correctly). Logs loudly when merging so the
    operator can see the LLM dropped a required cron.
    """
    crons = manifest.get("cron_jobs")
    if not isinstance(crons, list):
        # Validator will flag the missing/wrong-typed cron_jobs field separately.
        return []

    existing_names = {c.get("name") for c in crons if isinstance(c, dict)}
    added = []
    for canonical in TIER1_HYGIENE_CRONS:
        if canonical["name"] not in existing_names:
            crons.append(dict(canonical))
            added.append(canonical["name"])

    if added:
        print(
            f"[synth] auto-merged missing Tier-1 hygiene crons: {added}. "
            f"The LLM produced a manifest missing protocol-standard crons; "
            f"the synthesizer is enforcing them per protocol rules.",
            file=sys.stderr,
        )
        manifest["cron_jobs"] = crons
    return added


ALLOWED_NICHES = {
    "crypto_twitter_narrative_aggregator",
    "token_launcher",
    "wallet_banking_execution",
    "defi_auto_trader",
    "prediction_market_bettor",
    "autonomous_coding",
    "pay_per_call_x402_api",
    "a2a_service_marketplace",
    "smart_contract_audit",
    "nft_scanner",
    "onchain_casino",
    "revenue_backed_agent",
    "experimental",
}

NAME_RE   = re.compile(r"^[a-z][a-z0-9-]{2,29}$")    # kebab-case, 3-30 chars, starts lower
TICKER_RE = re.compile(r"^[A-Z][A-Z0-9]{2,5}$")      # 3-6 chars, uppercase, starts letter
USER_MD_REQUIRED_HEADERS = ["Name", "Ticker", "Niche"]


def validate_manifest(manifest: dict) -> list[str]:
    """Run cheap structural checks on the manifest. Returns list of issues.

    These validators catch shapes the LLM might botch even with the prompt
    spelled out: dropping fields, picking a niche outside the enum, naming
    the offspring something un-routable, sloppy cron entries, USER.md
    missing required headers. Auto-merge handles missing Tier-1 crons
    separately (see enforce_tier1_hygiene); this validator is the final
    safety net that catches the rest.
    """
    issues = []
    for f in REQUIRED_MANIFEST_FIELDS:
        if f not in manifest:
            issues.append(f"missing required field: {f}")

    # offspring_name: kebab-case, 3-30 chars
    name = manifest.get("offspring_name")
    if name is not None:
        if not isinstance(name, str) or not NAME_RE.match(name):
            issues.append(
                f"offspring_name {name!r} must match kebab-case [a-z][a-z0-9-]{{2,29}} "
                f"(no underscores, no caps, starts with a letter)"
            )

    # offspring_ticker: 3-6 uppercase chars, starts with a letter
    ticker = manifest.get("offspring_ticker")
    if ticker is not None:
        if not isinstance(ticker, str) or not TICKER_RE.match(ticker):
            issues.append(
                f"offspring_ticker {ticker!r} must be 3-6 uppercase chars starting "
                f"with a letter (matches ^[A-Z][A-Z0-9]{{2,5}}$)"
            )

    # locked_niche: must be in the canonical enum
    niche = manifest.get("locked_niche")
    if niche is not None and niche not in ALLOWED_NICHES:
        issues.append(
            f"locked_niche {niche!r} not in allowed set. "
            f"Pick one of: {sorted(ALLOWED_NICHES)}"
        )

    # soul_md: must carry the exact immutable LAYER 0 terminal goal sentence.
    # The full canonical text is 4 sentences (see SYNTHESIS_INSTRUCTIONS); we
    # check the load-bearing first sentence since the LLM might paraphrase the
    # rest but rarely rewrites the headline.
    soul = manifest.get("soul_md")
    if isinstance(soul, str):
        if "Maximize the value of $TOKEN_SELF" not in soul:
            issues.append("soul_md missing immutable LAYER 0 terminal goal")
        if "the Clawnch token launched at my birth" not in soul:
            issues.append("soul_md LAYER 0 sentence appears truncated or paraphrased")

    # user_md: must carry the required headers so downstream pages, spawn,
    # and registry registration can extract identity.
    user_md = manifest.get("user_md")
    if isinstance(user_md, str):
        for header in USER_MD_REQUIRED_HEADERS:
            # Allow both `**Name**:` and `Name:` to be permissive on formatting,
            # but require the literal token followed by `:`. read_offspring_identity
            # in spawn_offspring.py uses the `**Name**:` form, so flag the soft
            # form as a warning-not-error case (still works for templates but
            # spawn will fail). Strict: require the bolded form.
            if not re.search(rf"\*\*{header}\*\*\s*:", user_md):
                issues.append(
                    f"user_md missing required header `**{header}**:` "
                    f"(spawn_offspring.py expects bolded markdown form)"
                )

    # cron_jobs: shape check on each entry
    crons = manifest.get("cron_jobs")
    if not isinstance(crons, list):
        issues.append("cron_jobs must be a list")
    else:
        for i, c in enumerate(crons):
            if not isinstance(c, dict):
                issues.append(f"cron_jobs[{i}] is not an object")
                continue
            for required in ("name", "tier", "schedule", "prompt"):
                if required not in c:
                    issues.append(f"cron_jobs[{i}] missing field `{required}`")
            tier = c.get("tier")
            if tier not in (1, 2, 3):
                issues.append(f"cron_jobs[{i}].tier must be 1, 2, or 3 (got {tier!r})")

        present_tier1 = {c.get("name") for c in crons if isinstance(c, dict) and c.get("tier") == 1}
        missing_tier1 = TIER1_REQUIRED_NAMES - present_tier1
        if missing_tier1:
            # Should never reach here after enforce_tier1_hygiene runs, but kept
            # as a safety net in case anyone calls validate_manifest standalone.
            issues.append(
                f"cron_jobs missing required Tier-1 hygiene crons: {sorted(missing_tier1)}"
            )

    return issues


def compute_inheritance_hash(manifest: dict) -> str:
    """SHA-256 of the canonicalized inheritance bundle.

    Order: SOUL.md || MEMORY.md || USER.md || cron_jobs.json (canonical JSON).
    This is the hash each parent signs to attest the inheritance is authentic.
    Real protocol: each parent signs this hash with their gitlawb keypair via
    `gl identity sign <hex>` and submits the (parent_did, sig) pair to the
    registry. Two valid signatures = mating confirmed; the offspring may hatch.
    """
    h = hashlib.sha256()
    h.update(b"SOUL.md\n")
    h.update(manifest.get("soul_md", "").encode("utf-8"))
    h.update(b"\n----\nMEMORY.md\n")
    h.update(manifest.get("memory_md", "").encode("utf-8"))
    h.update(b"\n----\nUSER.md\n")
    h.update(manifest.get("user_md", "").encode("utf-8"))
    h.update(b"\n----\ncron_jobs.json\n")
    # Canonicalize cron_jobs JSON: sort keys, no whitespace variance
    h.update(json.dumps(manifest.get("cron_jobs", []), sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return h.hexdigest()


def attach_parent_dids(manifest: dict, parent_a_did: str | None, parent_b_did: str | None) -> None:
    """Stamp the offspring's manifest with the parents' gitlawb DIDs and the
    inheritance hash that the parents are expected to sign. Caller may pass
    the DIDs via CLI flags (--parent-a-did, --parent-b-did) or environment
    (BLENDER_PARENT_A_DID, BLENDER_PARENT_B_DID). If neither is available the
    fields are left empty and a TODO is logged so the operator can attach
    them later before the agent hatches.
    """
    manifest["parent_dids"] = {
        "parent_a": parent_a_did,
        "parent_b": parent_b_did,
    }
    manifest["inheritance_hash"] = compute_inheritance_hash(manifest)
    # Slot for signatures filled in by each parent agent post-hoc via `gl
    # identity sign <inheritance_hash>`. Empty until both parents sign.
    manifest["parent_signatures"] = {
        "parent_a": None,
        "parent_b": None,
    }
    if not parent_a_did or not parent_b_did:
        print(
            f"[synth] NOTE: parent DIDs not provided "
            f"(parent_a={parent_a_did!r}, parent_b={parent_b_did!r}). "
            f"Fill these via --parent-a-did/--parent-b-did or BLENDER_PARENT_*_DID env "
            f"so the inheritance is cryptographically anchored. The offspring's "
            f"inheritance_hash is recorded in raw_manifest.json regardless.",
            file=sys.stderr,
        )


def write_offspring(manifest: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "SOUL.md").write_text(manifest["soul_md"], encoding="utf-8")
    (out_dir / "MEMORY.md").write_text(manifest["memory_md"], encoding="utf-8")
    (out_dir / "USER.md").write_text(manifest["user_md"], encoding="utf-8")
    (out_dir / "cron_jobs.json").write_text(
        json.dumps(manifest["cron_jobs"], indent=2), encoding="utf-8"
    )
    (out_dir / "MATING_MANIFEST.md").write_text(
        "# Mating Manifest: "
        + f"{manifest['offspring_name']} ({manifest['offspring_ticker']})\n\n"
        + f"**Locked niche**: {manifest['locked_niche']}\n\n"
        + f"**Inheritance hash (SHA-256)**: `{manifest.get('inheritance_hash', '?')}`\n\n"
        + f"**Parent A DID**: `{manifest.get('parent_dids', {}).get('parent_a') or '(unattached)'}`\n"
        + f"**Parent B DID**: `{manifest.get('parent_dids', {}).get('parent_b') or '(unattached)'}`\n\n"
        + "## Synthesis notes\n\n"
        + manifest.get("synthesis_notes", "(no notes provided)")
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "raw_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    # Standalone inheritance_hash.txt so each parent agent can pipe it
    # directly into `gl identity sign` on their own machine.
    if "inheritance_hash" in manifest:
        (out_dir / "inheritance_hash.txt").write_text(
            manifest["inheritance_hash"] + "\n", encoding="utf-8"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Blender Synthesis Service prototype: compose an offspring's Mating Manifest from two parent agents"
    )
    parser.add_argument("parent_a", type=Path, help="Path to parent A directory")
    parser.add_argument("parent_b", type=Path, help="Path to parent B directory")
    parser.add_argument(
        "output", type=Path, help="Where to write the offspring directory"
    )
    parser.add_argument(
        "--model",
        default=os.environ.get(
            "BLENDER_SYNTH_MODEL", "nousresearch/hermes-3-llama-3.1-405b:free"
        ),
        help="Model id (default: free Hermes 3 405B on OpenRouter, or env BLENDER_SYNTH_MODEL)",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get(
            "BLENDER_SYNTH_BASE_URL", "https://openrouter.ai/api/v1"
        ),
        help="OpenAI-compatible base URL (default: OpenRouter, or env BLENDER_SYNTH_BASE_URL)",
    )
    parser.add_argument(
        "--parent-a-did",
        default=os.environ.get("BLENDER_PARENT_A_DID"),
        help="Parent A's gitlawb DID (did:gitlawb:z6Mk... or did:key:z6Mk...). "
             "Stamped into the offspring's raw_manifest. Fallback: env BLENDER_PARENT_A_DID.",
    )
    parser.add_argument(
        "--parent-b-did",
        default=os.environ.get("BLENDER_PARENT_B_DID"),
        help="Parent B's gitlawb DID. Stamped into the offspring's raw_manifest. "
             "Fallback: env BLENDER_PARENT_B_DID.",
    )
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get(
        "BLENDER_SYNTH_API_KEY"
    )
    if not api_key:
        print(
            "ERROR: No API key. Set OPENROUTER_API_KEY (preferred) or BLENDER_SYNTH_API_KEY.\n"
            "  Get a free key at https://openrouter.ai/ and run:\n"
            "      export OPENROUTER_API_KEY=sk-or-v1-...\n"
            "  Or, to point at a different OpenAI-compatible endpoint:\n"
            "      export BLENDER_SYNTH_BASE_URL=https://your.gateway/v1\n"
            "      export BLENDER_SYNTH_API_KEY=...\n",
            file=sys.stderr,
        )
        return 1

    if not args.parent_a.is_dir():
        print(f"ERROR: parent A directory not found: {args.parent_a}", file=sys.stderr)
        return 1
    if not args.parent_b.is_dir():
        print(f"ERROR: parent B directory not found: {args.parent_b}", file=sys.stderr)
        return 1
    if args.output.exists() and any(args.output.iterdir()):
        print(
            f"WARNING: output dir {args.output} already exists and is non-empty. "
            "Files will be overwritten.",
            file=sys.stderr,
        )

    print(f"[synth] reading parent A: {args.parent_a}")
    parent_a = read_parent(args.parent_a)
    print(f"[synth] reading parent B: {args.parent_b}")
    parent_b = read_parent(args.parent_b)

    prompt = compose_synthesis_prompt(parent_a, parent_b)
    print(f"[synth] synthesis prompt: {len(prompt)} chars (~{len(prompt) // 4} tokens)")

    print(f"[synth] calling LLM: {args.model} @ {args.base_url}")
    raw = call_llm(prompt, args.model, api_key, args.base_url)
    print(f"[synth] received {len(raw)} chars of output")

    try:
        manifest = parse_offspring(raw)
    except (ValueError, json.JSONDecodeError):
        # Dump the raw output so the user can recover it
        dump_path = args.output.parent / f"{args.output.name}_RAW_FAILED.txt"
        dump_path.parent.mkdir(parents=True, exist_ok=True)
        dump_path.write_text(raw, encoding="utf-8")
        print(
            f"[synth] FAILED to parse JSON. Raw output saved to {dump_path}",
            file=sys.stderr,
        )
        return 2

    # Enforce Tier-1 hygiene cron presence BEFORE validation so the validator
    # sees the corrected manifest. Auto-merges canonical entries for any cron
    # the LLM dropped; per protocol, no offspring is allowed to ship without
    # the full Tier-1 set.
    enforce_tier1_hygiene(manifest)

    # Phase 2c: stamp parent DIDs and compute the inheritance hash that each
    # parent will sign with their gitlawb keypair to certify this offspring.
    # Per protocol, no offspring may hatch until both parent signatures land.
    attach_parent_dids(manifest, args.parent_a_did, args.parent_b_did)

    issues = validate_manifest(manifest)
    if issues:
        print("[synth] WARNING: manifest validation issues:", file=sys.stderr)
        for issue in issues:
            print(f"  - {issue}", file=sys.stderr)
        print(
            "[synth] writing offspring files anyway so you can inspect.",
            file=sys.stderr,
        )

    print(
        f"[synth] offspring: {manifest.get('offspring_name', '?')} "
        f"({manifest.get('offspring_ticker', '?')})"
    )
    print(f"[synth] locked niche: {manifest.get('locked_niche', '?')}")
    print(f"[synth] crons: {len(manifest.get('cron_jobs', []))} jobs")

    print(f"[synth] writing offspring to {args.output}")
    write_offspring(manifest, args.output)

    print(f"[synth] done. inspect {args.output}/ to review the offspring.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
