# Dockerfile for the trendpilot Gen 0 founder (Hyperliquid trend trader).
#
# BUILD CONTEXT = repo root (so it can pull both the shared agent-template
# assets and the trendpilot persona). Deploy with:
#   flyctl deploy --config founders/trendpilot/fly_deploy/fly.toml \
#                 --dockerfile founders/trendpilot/fly_deploy/Dockerfile
# run from the repo root.

FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    HERMES_HOME=/opt/data \
    PLAYWRIGHT_BROWSERS_PATH=/opt/hermes/.playwright

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg git tini procps ripgrep ffmpeg \
        build-essential python3-dev libffi-dev nodejs npm sqlite3 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -u 10000 -m -d /opt/data hermes

# Python deps. hyperliquid-python-sdk (v0.23.0, verified 2026-05-30) provides
# the `hyperliquid` module; eth-account derives the agent wallet from the
# trade-only key. coincurve + websockets activate Nostr publishing.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        hermes-agent \
        "mcp>=1.2.0" \
        coincurve \
        websockets \
        hyperliquid-python-sdk \
        eth-account

# Pre-pull clawnch MCP (bin is `clawnch-mcp`).
RUN npm install -g "clawnch-mcp-server@^1" && which clawnch-mcp

# gitlawb CLI for did:gitlawb identity + MCP.
RUN curl -fsSL https://gitlawb.com/install.sh | GITLAWB_INSTALL_DIR=/usr/local/bin sh \
    && gl --version

WORKDIR /opt/hermes

# Shared agent-template assets (MCPs incl hyperliquid_mcp.py, skills incl
# hyperliquid_trade.md, templates, bootstrap).
COPY --chown=hermes:hermes agent-template/mcp/ /opt/hermes/mcp/
COPY --chown=hermes:hermes agent-template/skills/ /opt/hermes/skills/
COPY --chown=hermes:hermes agent-template/templates/ /opt/hermes/templates/
COPY --chown=hermes:hermes agent-template/bootstrap_crons.py /opt/hermes/bootstrap_crons.py

# trendpilot persona.
COPY --chown=hermes:hermes founders/trendpilot/config.yaml /opt/hermes/config.yaml
COPY --chown=hermes:hermes founders/trendpilot/SOUL.md /opt/hermes/SOUL.md
COPY --chown=hermes:hermes founders/trendpilot/MEMORY.md /opt/hermes/MEMORY.md
COPY --chown=hermes:hermes founders/trendpilot/USER.md /opt/hermes/USER.md
COPY --chown=hermes:hermes founders/trendpilot/cron_jobs.json /opt/hermes/cron_jobs.json

# Strip CRLF defensively so the shebang execs on Linux.
COPY --chmod=0755 founders/trendpilot/fly_deploy/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh

EXPOSE 8642
ENTRYPOINT ["tini", "--", "/usr/local/bin/entrypoint.sh"]
CMD ["hermes", "gateway", "run"]
