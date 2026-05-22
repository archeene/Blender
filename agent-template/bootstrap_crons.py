"""
Bootstrap script. Runs once at agent startup. Reads cron_jobs.json and
registers each cron with the Hermes Agent runtime via the `hermes cron add`
CLI. Idempotent: skips any cron name that already exists.

Lives at /agent-template/bootstrap_crons.py inside the Modal container.
Called from modal_deploy.py on the first container boot.
"""
import json
import subprocess
import sys
from pathlib import Path


CRON_FILE = Path(__file__).parent / "cron_jobs.json"


def list_existing_cron_names() -> set[str]:
    """Return the set of names of crons already registered with this Hermes Agent."""
    try:
        result = subprocess.run(
            ["hermes", "cron", "list", "--json"],
            capture_output=True,
            text=True,
            check=True,
        )
        existing = json.loads(result.stdout)
        return {c["name"] for c in existing if "name" in c}
    except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError):
        # First run, no crons yet, or Hermes Agent not in the path.
        return set()


def register_cron(name: str, schedule: str, prompt: str) -> bool:
    """Register one cron via `hermes cron add`. Returns True on success."""
    cmd = [
        "hermes",
        "cron",
        "add",
        schedule,
        prompt,
        "--name",
        name,
    ]
    try:
        subprocess.run(cmd, check=True)
        print(f"[bootstrap] registered cron: {name}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[bootstrap] FAILED to register cron {name}: {e}", file=sys.stderr)
        return False


PINNED_SKILLS = [
    # Skills the Curator must never auto-archive. These are protocol-standard
    # and load-bearing for every Blender offspring.
    "protocol_sync",
    "publish_profile",
    "clawnch_launch",
    "royalty_cascade",
    "death_check",
]


def pin_skill(name: str) -> bool:
    """Pin a skill via `hermes curator pin <name>`. Idempotent; safe to call
    on already-pinned skills (Hermes returns success either way)."""
    try:
        subprocess.run(["hermes", "curator", "pin", name], check=True)
        print(f"[bootstrap] pinned skill: {name}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[bootstrap] WARN: could not pin skill '{name}': {e}", file=sys.stderr)
        return False
    except FileNotFoundError:
        print(f"[bootstrap] WARN: hermes CLI not on PATH; skipping pin for {name}", file=sys.stderr)
        return False


def main() -> int:
    if not CRON_FILE.exists():
        print(f"[bootstrap] no cron_jobs.json at {CRON_FILE}, nothing to do.")
        return 0

    jobs = json.loads(CRON_FILE.read_text(encoding="utf-8"))
    existing = list_existing_cron_names()
    print(f"[bootstrap] {len(existing)} cron(s) already registered: {sorted(existing)}")

    registered = 0
    skipped = 0
    failed = 0
    for job in jobs:
        name = job["name"]
        if name in existing:
            print(f"[bootstrap] skipping {name} (already registered)")
            skipped += 1
            continue
        ok = register_cron(name=name, schedule=job["schedule"], prompt=job["prompt"])
        if ok:
            registered += 1
        else:
            failed += 1

    print(f"[bootstrap] done. registered={registered} skipped={skipped} failed={failed}")

    # Pin protocol-standard skills so the Curator's 90-day auto-archive
    # heuristic never removes them during low-activity periods.
    print(f"[bootstrap] pinning {len(PINNED_SKILLS)} protocol-standard skill(s)")
    for s in PINNED_SKILLS:
        pin_skill(s)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
