# Deploy a Blender offspring on Fly.io

This is the **recommended deploy path** because it mirrors the pattern already running on your `blender-agent` Fly app (deployed May 12, the protocol's Gen 0 matchmaker entity). Each offspring gets its own Fly app + Volume; offspring run as siblings of the Gen 0 Blender, not replacements.

Prerequisites you already have (verified by `flyctl orgs list && flyctl apps list`):

- `flyctl` installed and authenticated as `tobias@velocityaipartners.ai`
- Personal Fly org with the existing `blender-agent`, `imasocial-hermes`, etc. apps
- Bankr account + `BANKR_API_KEY` already in `blender-agent`'s secrets
- GLM (Zhipu) inference: `GLM_API_KEY` + `GLM_BASE_URL` already in `blender-agent`'s secrets

## Step 1: Spawn the deploy directory

From the repo root:

```
cd C:\Users\PRIME\Blender\reproduction-test
python synthesis\spawn_offspring.py offspring\run_001 offspring\run_001\deploy
```

This writes `offspring/run_001/deploy/` with everything needed for a Fly deploy:

```
deploy/
  SOUL.md MEMORY.md USER.md cron_jobs.json   <- the offspring's identity (synthesis output)
  config.yaml                                <- Hermes config (defaults to GLM provider)
  bootstrap_crons.py
  Dockerfile                                 <- copies from agent-template/fly_deploy/
  entrypoint.sh                              <- bootstraps the volume on first boot
  fly.toml                                   <- rendered with the offspring's app name
  modal_deploy.py                            <- Modal alternative, ignore if using Fly
  mcp/   skills/   templates/                <- shared agent-template assets
  README.md
  requirements.txt
  .env.example
```

The fly.toml will have `app = "blender-yield-aggregator"` (or whatever the offspring's name is from synthesis) and the volume named `blender_yield_aggregator_data`.

## Step 2: Create the Fly app

```
cd offspring\run_001\deploy
flyctl apps create blender-yield-aggregator --org personal
```

This reserves the app slot in your Fly account. No machine starts yet.

## Step 3: Copy secrets from the existing blender-agent

The Gen 0 Blender app has the right credentials already. Easiest path: read them and replay onto the new app. Fly doesn't let you read secret values back (security), so you'll need to paste them from your records.

Required secrets:

```
flyctl secrets set --app blender-yield-aggregator `
    GLM_API_KEY=... `
    GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4 `
    BANKR_API_KEY=... `
    API_SERVER_KEY=...
```

Optional (only if the agent should post / publish):

```
flyctl secrets set --app blender-yield-aggregator `
    NEYNAR_API_KEY=... `
    NEYNAR_SIGNER_UUID=... `
    GITHUB_TOKEN=github_pat_...
```

If you don't have these values on hand, grab them from your Bankr / Neynar / GitHub dashboards. The existing `blender-agent` app's secret list (`flyctl secrets list --app blender-agent`) tells you which keys exist but not their values.

## Step 4: Deploy

```
flyctl deploy --app blender-yield-aggregator
```

Fly builds the Dockerfile (~2-3 min first time), creates the 5GB Volume, mounts at `/opt/data`, starts the gateway. Watch the build:

```
flyctl logs --app blender-yield-aggregator
```

You should see:

```
[entrypoint] seeded config.yaml
[entrypoint] seeded SOUL.md
[entrypoint] seeded MEMORY.md
[entrypoint] seeded USER.md
[entrypoint] registering crons
[bootstrap] registered cron: protocol_sync
[bootstrap] registered cron: monitoring_scan
... (9 crons total)
[bootstrap] done. registered=9 skipped=0 failed=0
[entrypoint] launching: hermes gateway run
```

After about 60 seconds the gateway is up. Health check at `https://blender-yield-aggregator.fly.dev/health` should return 200.

## Step 5: Verify the first hour

### Logs

```
flyctl logs --app blender-yield-aggregator
```

Within an hour expect: `protocol_sync` fires once (processes the channel-launch bulletin), `monitoring_scan` fires 4 times (every 15min, no-op early on), `hourly_action` fires once at HH:30.

### Inspect Volume state

```
flyctl ssh console --app blender-yield-aggregator
# inside the container:
ls /opt/data/.hermes/
cat /opt/data/.hermes/memories/MEMORY.md
sqlite3 /opt/data/data/registry.db "SELECT name FROM agents;"
ls /opt/data/data/moltbook/posts/yield-aggregator/
```

### Manually trigger a cron for debugging

```
flyctl ssh console --app blender-yield-aggregator
hermes cron list                      # show all 9 registered crons
hermes cron run protocol_sync         # fire it now instead of waiting
hermes cron run publish_profile       # test the GitHub publish flow
```

## Step 6: Iterate

If a cron is misbehaving, fix the prompt in `cron_jobs.json` in the deploy dir on your laptop, then redeploy:

```
flyctl deploy --app blender-yield-aggregator
```

The Volume persists across deploys, so the agent's SOUL/MEMORY/USER state isn't reset. Only the build-time files (Dockerfile-baked) refresh. To reset the agent (rare):

```
flyctl volumes destroy blender_yield_aggregator_data --app blender-yield-aggregator
# next deploy creates a fresh volume
```

## Cost

Per the existing blender-agent's machine size (1x shared-cpu-1x, 2GB RAM, 5GB volume), each agent costs roughly:

- ~$2-4/month on Fly.io's shared-cpu pricing (a single machine running 24/7)
- ~$0 in GLM inference if using GLM's free quota / Zhipu's promotional credits
- ~$1-3 in Bankr API + Clawnch fees + Neynar (depending on usage)

Total: ~$5-10/month per offspring. Cheaper than Modal at the same uptime.

## Comparison: existing blender-agent vs new yield-aggregator

| | blender-agent | blender-yield-aggregator |
|-|-|-|
| Identity | Blender (Gen 0 matchmaker) | yield-aggregator (Gen 1 offspring) |
| SOUL.md location | `docker/SOUL.md` in hermes-agent source | `/opt/data/.hermes/SOUL.md` in Volume |
| Locked niche | matchmaker / protocol management | defi_auto_trader |
| Built from | full hermes-agent source (Dockerfile in source repo) | lightweight pip-install of hermes-agent (Dockerfile in agent-template) |
| Telegram bot | yes (TELEGRAM_BOT_TOKEN) | optional (not in v0) |
| Bankr wired | yes | yes (same key) |
| Self-publishes profile | no | yes (publish_profile cron) |

Both apps share the same Fly account, same Bankr account, same GLM provider. They are operationally independent: one is the protocol's root, the other is a descendant.

## What this does NOT cover

- Real Clawnch token launch (separate one-time setup per offspring once you decide on the token utility)
- Actual x402 endpoint with paid handler logic (the agent generates this itself once it has product clarity)
- Multi-region failover (single region ORD is fine for v0)
- Cross-agent messaging via Fly internal networking (deferred until multiple offspring exist)
- The Bankr CLI for manual x402 deploys (Hermes has shell access; the agent shells out to `bankr` directly)

## Troubleshooting

### Build fails on `playwright install`

Playwright dep is large and sometimes flakes. Comment out the playwright install line in `Dockerfile` and redeploy. Browser-automation skills won't work, but text-API skills (Farcaster via Neynar, Bankr, GitHub) will.

### Health check fails repeatedly

`hermes gateway run` may be crashing on startup. Check logs for `bootstrap_crons.py` errors. Usually means a cron prompt has a syntax issue or `hermes cron add` flag mismatch.

### Volume permission errors

`entrypoint.sh` runs as root, fixes ownership, then drops to the hermes user. If you see `EACCES` errors, the volume was created with the wrong UID. Destroy and recreate the volume (see Step 6 above).

### Secrets not picked up

Confirm with `flyctl secrets list --app blender-yield-aggregator`. Secrets only refresh on machine restart; if you changed them post-deploy, run `flyctl machine restart <machine-id>`.

### GLM rate limited

Zhipu's free tier has hourly limits. Switch the agent's config.yaml to a different provider temporarily (OpenRouter, Anthropic, etc.) by editing `config.yaml` in the deploy dir and redeploying. Or pay for GLM API access at https://bigmodel.cn.
