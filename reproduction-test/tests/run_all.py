"""Run every test file in this directory and report a combined pass/fail tally.

Usage:
    python reproduction-test/tests/run_all.py

Exit status: 0 = all pass, 1 = at least one failure, 2 = harness error.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Each entry: (display_name, script_path)
SUITES = [
    ("registry_mcp",       HERE / "test_registry.py"),
    ("synthesize_offspring", HERE / "test_synthesize.py"),
    ("hyperliquid_limits", HERE / "test_hyperliquid_limits.py"),
]


def main() -> int:
    overall_fail = False
    for name, path in SUITES:
        if not path.exists():
            print(f"[run_all] skipping missing suite: {name} ({path})", file=sys.stderr)
            continue
        print(f"\n========== {name} ==========")
        proc = subprocess.run([sys.executable, str(path)], capture_output=False)
        if proc.returncode != 0:
            overall_fail = True
            print(f"[run_all] {name} FAILED (exit {proc.returncode})", file=sys.stderr)
    print()
    if overall_fail:
        print("[run_all] SOME SUITES FAILED")
        return 1
    print("[run_all] ALL SUITES PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
