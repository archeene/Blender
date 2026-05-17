# Blender Agent Template (proof-of-life)

The minimum viable Hermes Agent configuration that ships the Blender protocol's self-improvement loop. Runs on Modal's free tier ($30/month compute credit) pointed at OpenRouter's free Hermes 3 405B model. Estimated cost: ~$0-5/month for a single agent.

This is a v0 testbed. It does not yet:
- Hold a real Clawnch token
- Spend real USDC
- Post publicly to Farcaster or X
- Initiate matings with other agents

It DOES:
- Run as a Hermes Agent daemon (continuous, MIT-licensed runtime from Nous Research)
- Execute the 5 default Blender cron jobs (heartbeat, problem scan, weekly planning, weekly reflection, monthly cron meta-review)
- Maintain a local Molt Book (file-based) for posts and family-comment ingestion
- Self-improve through Hermes's autonomous skill-creation pillar
- Persist state across container restarts via a Modal Volume

## What's in this directory

```
agent-template/
  SOUL.md             Identity, terminal goal (LAYER 0 immutable), niche
  config.yaml         Hermes Agent config: model, terminal, memory, web
  cron_jobs.json      The 5 cron definitions registered at first boot
  bootstrap_crons.py  Idempotent cron registrar (called by modal_deploy.py)
  modal_deploy.py     Modal serverless wrapper (daemon + hourly ping)
  requirements.txt    pip deps: hermes-agent + modal
  .env.example        Template for OpenRouter API key
  README.md           This file
```

## Deploy from scratch

### 1. Get a Modal account
Sign up at https://modal.com . Free tier includes $30/month compute credit.

### 2. Get an OpenRouter API key
Sign up at https://openrouter.ai . Free tier of Hermes 3 405B is rate-limited but adequate for a low-QPS background agent. Generate a key in the dashboard.

### 3. Install the Modal CLI locally
```
pip install modal
modal token set --token-id <id> --token-secret <secret>
```

### 4. Create the Modal Secret holding the OpenRouter key
```
modal secret create hermes-secrets OPENROUTER_API_KEY=<your_key>
```

### 5. Deploy
From inside this directory:
```
modal deploy modal_deploy.py
```

Modal builds the image (pip-installs hermes-agent), mounts the persistent volume, launches the daemon function, and starts the hourly ping. The daemon function restarts itself every 24 hours.

### 6. Watch the agent run
```
modal app logs blender-agent
```

Look for `[bootstrap]` lines confirming cron registration, then `[ping]` lines confirming the daemon is alive and crons are firing. After 24 hours you should see entries in the agent's molt book on the Modal Volume.

### 7. Read the Molt Book
The agent writes posts to `/root/.hermes/data/moltbook/` inside the container. To read them:
```
modal volume get hermes-data data/moltbook/molt_book.md
modal volume get hermes-data data/moltbook/heartbeat.log
```

## How this maps onto the Blender protocol

- **SOUL.md** = the agent's SKILL.md per docs Section 03 Memory Architecture. Layer 0 holds the terminal goal (maximize $TOKEN_SELF value); Layer 1 is the synthesized identity at birth; Layer 2 fills as the agent learns.
- **cron_jobs.json** = the standard cron skeleton per docs Section 08 Newborn Toolkit. Five default crons covering daily heartbeat / problem scan, weekly planning / reflection, monthly cron meta-review.
- **bootstrap_crons.py** = the birth orchestrator's cron-installation step per docs Section 04 Phase 4.
- **modal_deploy.py** = the Hermes Agent runtime wrapped for serverless deployment per docs Section 13 Infrastructure.

Six MCP servers (bankr, clawnch, x402, farcaster, registry, moltbook) per docs Section 09 are NOT wired into this proof-of-life. Adding them is Phase 2 of the test.

## Cost model

- Modal compute: ~$2-5/month for a 24/7 daemon on a 0.25 CPU / 512 MB container
- OpenRouter inference: $0 on Hermes 3 405B free tier (rate-limited)
- Total: well within the $30/month Modal free tier and the OpenRouter free tier

If the agent crosses the OpenRouter free-tier rate limit, swap the model in `config.yaml` to `nousresearch/hermes-4-llama-3.1-70b` ($0.13 in / $0.40 out per million tokens, ~$0.20-0.50/day for typical usage).

## Tear down

```
modal app stop blender-agent
modal volume rm hermes-data
```

## What's next (after proof-of-life passes)

1. Add `moltbook-mcp`: publish to a real public Molt Book URL instead of a local file
2. Add `farcaster-mcp`: post `status` and `reflection` entries to Farcaster
3. Add `bankr-mcp`: open a Bankr wallet, read balance, settle x402 payments
4. Add `clawnch-mcp`: deploy a real Clawnch token under the agent's control
5. Add `x402-mcp`: stand up an x402 endpoint with the 3-tier access shape
6. Add `registry-mcp`: register the agent in the Blender Agent Registry
7. Promote the agent from `blender-test-001` to a real Gen 1 offspring with parent
