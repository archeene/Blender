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
import json
import os
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
   - Tier 1 hygiene (IMMUTABLE, same across all offspring): monitoring_scan (*/15 * * * *), nightly_triage (0 2 * * *), weekly_planning (0 9 * * 1), weekly_reflection (0 17 * * 5).
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


def validate_manifest(manifest: dict) -> list[str]:
    """Run cheap structural checks on the manifest. Returns list of issues."""
    issues = []
    for f in REQUIRED_MANIFEST_FIELDS:
        if f not in manifest:
            issues.append(f"missing required field: {f}")
    if "cron_jobs" in manifest and not isinstance(manifest["cron_jobs"], list):
        issues.append("cron_jobs must be a list")
    if "soul_md" in manifest:
        if "Maximize the value of $TOKEN_SELF" not in manifest["soul_md"]:
            issues.append("soul_md missing immutable LAYER 0 terminal goal")
    if "cron_jobs" in manifest and isinstance(manifest["cron_jobs"], list):
        tier1_names = {
            "monitoring_scan",
            "nightly_triage",
            "weekly_planning",
            "weekly_reflection",
        }
        present_tier1 = {
            c.get("name") for c in manifest["cron_jobs"] if c.get("tier") == 1
        }
        missing_tier1 = tier1_names - present_tier1
        if missing_tier1:
            issues.append(
                f"cron_jobs missing required Tier-1 hygiene crons: {sorted(missing_tier1)}"
            )
    return issues


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
        + "## Synthesis notes\n\n"
        + manifest.get("synthesis_notes", "(no notes provided)")
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "raw_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
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
