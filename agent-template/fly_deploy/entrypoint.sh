#!/bin/bash
# Fly.io entrypoint for a Blender offspring agent.
# Bootstraps the persistent Volume on first boot, registers crons, then exec
# whatever was passed as CMD (default: hermes gateway run).
set -e

HERMES_HOME="${HERMES_HOME:-/opt/data}"
HERMES_BUILD="/opt/hermes"

# Ensure volume directory exists and is writable.
mkdir -p "$HERMES_HOME/.hermes/memories" "$HERMES_HOME/.hermes/skills" "$HERMES_HOME/.hermes/templates" "$HERMES_HOME/data"

# First-boot seeding: copy build-time defaults into the volume only if not
# already present. Lets the agent persist its own evolution across restarts
# without us overwriting changes on every deploy.
seed() {
    local src="$1" dst="$2" label="$3"
    if [ ! -f "$dst" ]; then
        cp "$src" "$dst" && echo "[entrypoint] seeded $label"
    else
        echo "[entrypoint] kept existing $label (volume already has it)"
    fi
}

seed "$HERMES_BUILD/config.yaml"      "$HERMES_HOME/.hermes/config.yaml"     "config.yaml"
seed "$HERMES_BUILD/SOUL.md"          "$HERMES_HOME/.hermes/SOUL.md"         "SOUL.md"
seed "$HERMES_BUILD/MEMORY.md"        "$HERMES_HOME/.hermes/memories/MEMORY.md"  "MEMORY.md"
seed "$HERMES_BUILD/USER.md"          "$HERMES_HOME/.hermes/memories/USER.md"    "USER.md"

# MCP servers, skills, templates: rsync so updates from each deploy reach the volume
# (whereas SOUL.md / MEMORY.md / USER.md are agent-owned once initialized).
cp -rn "$HERMES_BUILD/mcp/."       "$HERMES_HOME/.hermes/mcp/"       2>/dev/null || true
cp -r  "$HERMES_BUILD/skills/."    "$HERMES_HOME/.hermes/skills/"    2>/dev/null || true
cp -r  "$HERMES_BUILD/templates/." "$HERMES_HOME/.hermes/templates/" 2>/dev/null || true

# Idempotent cron registration. Safe to re-run on every boot.
echo "[entrypoint] registering crons"
python "$HERMES_BUILD/bootstrap_crons.py" || \
    echo "[entrypoint] WARN: bootstrap_crons.py exited non-zero; continuing"

# Hand off to whatever CMD was set (hermes gateway run by default).
echo "[entrypoint] launching: $*"
exec "$@"
