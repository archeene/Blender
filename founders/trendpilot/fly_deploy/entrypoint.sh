#!/bin/bash
# Fly.io entrypoint for trendpilot (Gen 0 Hyperliquid trend trader).
# Seeds the persistent volume on first boot, issues a did:gitlawb + Nostr
# identity, registers crons, then execs the gateway.
set -e

HERMES_HOME="${HERMES_HOME:-/opt/data}"
HERMES_BUILD="/opt/hermes"

mkdir -p "$HERMES_HOME/.hermes/memories" "$HERMES_HOME/.hermes/skills" \
         "$HERMES_HOME/.hermes/templates" "$HERMES_HOME/data" \
         "$HERMES_HOME/.gitlawb" "$HERMES_HOME/.nostr"

# First-boot seeding: copy build-time defaults into the volume only if absent,
# so the agent's own evolution persists across restarts.
seed() {
    local src="$1" dst="$2" label="$3"
    if [ ! -f "$dst" ]; then
        cp "$src" "$dst" && echo "[entrypoint] seeded $label"
    else
        echo "[entrypoint] kept existing $label"
    fi
}

seed "$HERMES_BUILD/config.yaml"  "$HERMES_HOME/.hermes/config.yaml"           "config.yaml"
seed "$HERMES_BUILD/SOUL.md"      "$HERMES_HOME/.hermes/SOUL.md"               "SOUL.md"
seed "$HERMES_BUILD/MEMORY.md"    "$HERMES_HOME/.hermes/memories/MEMORY.md"    "MEMORY.md"
seed "$HERMES_BUILD/USER.md"      "$HERMES_HOME/.hermes/memories/USER.md"      "USER.md"
seed "$HERMES_BUILD/cron_jobs.json" "$HERMES_HOME/.hermes/cron_jobs.json"      "cron_jobs.json"

# MCPs / skills / templates: refresh from each deploy.
cp -r  "$HERMES_BUILD/mcp/."       "$HERMES_HOME/.hermes/mcp/"       2>/dev/null || true
cp -r  "$HERMES_BUILD/skills/."    "$HERMES_HOME/.hermes/skills/"    2>/dev/null || true
cp -r  "$HERMES_BUILD/templates/." "$HERMES_HOME/.hermes/templates/" 2>/dev/null || true

export HOME="$HERMES_HOME"

# gitlawb identity (idempotent; fail-soft so an alpha-network hang can't block).
if command -v gl >/dev/null 2>&1; then
    if [ ! -f "$HERMES_HOME/.gitlawb/identity.pem" ]; then
        echo "[entrypoint] issuing did:gitlawb"
        gl identity new 2>&1 || echo "[entrypoint] WARN: gl identity new failed; continuing"
    fi
    if [ -f "$HERMES_HOME/.gitlawb/identity.pem" ]; then
        DID="$(gl identity show 2>/dev/null || true)"
        [ -n "$DID" ] && echo "[entrypoint] gitlawb DID: $DID"
        timeout 30 gl register 2>&1 || echo "[entrypoint] WARN: gl register failed/timed out"
    fi
fi

# Nostr identity (idempotent; non-fatal).
echo "[entrypoint] initializing Nostr identity"
python "$HERMES_BUILD/mcp/nostr_mcp.py" --init 2>&1 | sed 's/^/[entrypoint] nostr: /' || \
    echo "[entrypoint] WARN: nostr init non-zero; continuing"

# Report the trading safety posture so it's visible in logs on every boot.
echo "[entrypoint] HYPERLIQUID_NETWORK=${HYPERLIQUID_NETWORK:-testnet} TRADING_ENABLED=${HYPERLIQUID_TRADING_ENABLED:-false}"

# Idempotent cron registration + skill pinning.
echo "[entrypoint] registering crons"
python "$HERMES_BUILD/bootstrap_crons.py" || \
    echo "[entrypoint] WARN: bootstrap_crons.py exited non-zero; continuing"

echo "[entrypoint] launching: $*"
exec "$@"
