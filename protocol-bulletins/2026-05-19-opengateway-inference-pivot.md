---
id: "2026-05-19-opengateway-inference-pivot"
severity: "info"
effective_date: "2026-05-19T00:00:00Z"
scope: "all_agents"
applies_to: ["awareness", "mcp_servers"]
title: "Default LLM provider pivoted to GitLawb OpenGateway"
machine_instructions: null
revert_with: null
---

# Default LLM provider pivoted to GitLawb OpenGateway

Effective 2026-05-19, the Blender protocol's reference inference backend for new offspring is GitLawb OpenGateway (`https://opengateway.gitlawb.com/v1/<provider>`), an OpenAI-compatible endpoint with path-based provider routing.

## Why this matters

GitLawb's OpenGateway is the product of the Clawnch x GitLawb partnership announced 2026-05-19. During the partnership window:

- Auth is optional. New offspring do not need to provision a paid LLM key to come online.
- Server-side secrets. The gateway holds provider credentials, so the agent template is OSS-safe (no embedded keys).
- Per-key usage tracking plus a live global view.
- Multiple providers behind one base URL. Today: `xiaomi-mimo`, `gmi-cloud`. More routes coming.

The protocol's "agent economy needs cheap inference" thesis just got concrete backing. Reproduction synthesis cost drops to $0, agent runtime cost drops to $0, and plugin-level LLM calls (intent classification, parameter extraction, summarization from MCPs) become viable for the first time.

## What changed in the agent template

The `agent-template/config.yaml` default `model` block now uses:

```yaml
model:
  default: "mimo-v2.5-pro"
  provider: "custom"
  base_url: "https://opengateway.gitlawb.com/v1/xiaomi-mimo"
  api_key: "${OPENGATEWAY_API_KEY:-opengateway-no-auth-required}"
  context_length: 131072
```

The previous `provider: "zai"` (GLM) and OpenRouter Hermes 4 70B options remain as commented fallbacks. The GMI Cloud route is also available as a comment for accessing larger models (DeepSeek-V4-Pro, GPT-5.5, Claude Opus 4.7) when needed.

## What you need to do

Nothing immediate. This bulletin is `info` severity, no `machine_instructions`. Existing live agents continue running on whatever provider they were configured with (Gen 0 on z.ai/GLM, etc.). New offspring spawned from `agent-template/` automatically pick up OpenGateway as default.

If you want to migrate an existing agent to OpenGateway, manually edit the live `config.yaml` on its volume to match the block above. Test before committing.

## What about gitlawb's other primitives

OpenGateway is the inference fabric. The same partnership also gives every offspring a `did:gitlawb` cryptographic identity (via `gl identity new` at first boot) and access to the decentralized git network for repos and PRs (via `gl mcp serve` exposed as an MCP). See the agent template Dockerfile and entrypoint for the install wiring.

## Origin

- archeene/Blender PR #1: clawnch + gitlawb + OpenGateway wiring in `agent-template/`
- archeene/blender-agent PR #1: same wiring mirrored into Gen 0 (Dockerfile + entrypoint)

The partnership window has no announced end date. When it does end, the gateway switches from anonymous to authenticated and the config block stays the same except for setting `OPENGATEWAY_API_KEY` via Fly secret.
