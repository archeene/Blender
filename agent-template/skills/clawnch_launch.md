---
name: clawnch_launch
description: One-time launch of the agent's $TOKEN_SELF on Clawnch (Base). Idempotent. Records the resulting token contract address into USER.md and the agent registry. After successful launch, future invocations are no-ops.
trigger: cron `clawnch_launch` (Tier 3, weekly safety check) or manual via `hermes cron run clawnch_launch`. Also called by hatching workflow on first boot.
required_tools: clawnch MCP (clawnch_get_skill, clawnch_upload_image, clawnch_launch_token, clawnch_list_launches), bankr MCP (get_wallet_balance for the launch wallet), blender-moltbook MCP (publish_post), blender-registry MCP (update_agent_state to record token_address), farcaster-post MCP (for Moltx/4claw posting path).
required_env: optional CLAWNCH_PREFER_MOLTBOOK_KEY for the API-driven path; otherwise the Moltx/4claw social-post path needs no extra env.
---

# Skill: clawnch_launch

I launch my $TOKEN_SELF on the Clawnch platform exactly once, then keep that token address recorded in my identity files so every future cron, royalty distribution, and customer-facing message references the real contract.

## Pre-flight (always run first)

1. **Check if I've already launched.** Read USER.md for a `token_address` field. If it's a non-empty `0x...` string, call `clawnch_list_launches` filtered by my agent name and confirm the address still resolves to a live token. If both check out: log "already launched" to `clawnch_launch_log.md`, publish a single `status` post to Molt Book on the first idempotent skip (not every cycle), and return without doing anything.

2. **Confirm wallet readiness.** Call `bankr.get_wallet_balance`. If the operating wallet has < the platform-required minimum to cover gas on Base, publish a `needs_input` post tagged `clawnch_launch_blocked` to Molt Book and exit. Do NOT proceed with a launch I cannot pay for.

3. **Read the canonical Clawnch protocol.** Call `clawnch.clawnch_get_skill` to fetch the current launch protocol. The protocol's signals (image requirements, post format, fee-claiming address, supported launch surfaces) take precedence over anything in this skill file. If they conflict, follow what `clawnch_get_skill` returned and log the divergence.

## Step-by-step launch

4. **Compose identity payload from SOUL.md + USER.md**:
   - `name`: my agent name, kebab-case (e.g. `yield-aggregator`)
   - `symbol`: my ticker, 3-6 uppercase chars (e.g. `YAGG`)
   - `description`: one-sentence summary of my niche + value proposition, lifted verbatim from SOUL.md Layer 1
   - `wallet`: my operating wallet address (read from `bankr.get_wallet_balance` response)
   - `image_url`: see step 5

5. **Generate the launch image.** Two acceptable paths:
   - (a) If `templates/launch_image.svg` exists, render it with my name/ticker/colors and convert to PNG.
   - (b) Otherwise, use a 1024x1024 solid-color square with my ticker in display font (Cormorant Garamond if available, else system serif) centered on a deep-green or violet background (match my SOUL.md voice — analytical=violet, signal-channel=amber, etc.).
   Call `clawnch.clawnch_upload_image` with the result. Capture the returned `https://iili.io/...` URL.

6. **Submit the launch.** Choose the surface based on `CLAWNCH_PREFER_MOLTBOOK_KEY` env:
   - **If set**: call `clawnch.clawnch_launch_token` with `moltbook_key` from env and a `post_id` you generate on Moltbook first (per `clawnch_get_skill` Moltbook flow).
   - **Otherwise (default)**: compose a single Farcaster cast via `farcaster-post.publish_cast`. Body must start with `!clawnch` per the platform's parser, then include the name, symbol, wallet, description, and image URL on separate lines. The Clawnch scanner watches Moltx/4claw casts for `!clawnch` and triggers the launch within 60 seconds.

7. **Wait + verify (max 5 minutes total).** Poll `clawnch.clawnch_list_launches` every 30 seconds filtered by my agent name. As soon as the launch shows up with a non-empty `token_address`, capture it. If after 5 minutes the launch still isn't visible:
   - Publish a `needs_input` post tagged `clawnch_launch_failed` to Molt Book with the launch payload + Cast URL + timestamps so a human can investigate.
   - Do NOT retry blindly. The platform has a 1-launch-per-24h-per-agent rate limit (per `clawnch_get_skill`); retrying could waste the day's quota.

8. **Record the address everywhere.** Once you have a `token_address`:
   - Append to USER.md under STATE: `token_address: 0x...` and `token_launched_at: <ISO timestamp>`. Use the file-edit tools so the YAML/markdown structure stays valid.
   - Call `blender-registry.update_agent_state` with `token_address` if the registry tool supports it; otherwise call `register_agent` again with the same fields (idempotent re-register) so the address can land via a later registry schema migration.
   - Publish a `milestone` post to Molt Book tagged `clawnch_launched` with: name, symbol, contract address, Cast URL, launch image URL. This is a once-in-a-lifetime event for the agent; the Molt Book milestone is the canonical record.

9. **Update the protocol-standard claim address.** Per `clawnch_get_skill`, 80% of trading fees route to the wallet I declared at launch. Confirm that wallet matches my current `bankr` operating wallet. If they ever diverge (e.g., a wallet rotation in a future protocol bulletin), publish a `needs_input` post tagged `clawnch_fee_route_mismatch` so a human can rotate the on-chain claim address.

## Boundary conditions

- **Wallet unfunded**: skip launch, publish `needs_input`, retry on the next scheduled run. No loop, no fake address.
- **clawnch_get_skill unreachable**: log error, skip this cycle, retry next time. Never launch using a stale local copy of the protocol; always re-fetch.
- **Token already launched per USER.md but no longer in clawnch_list_launches**: publish `needs_input` tagged `clawnch_token_disappeared`. Do not auto-relaunch — could be a network glitch and re-launching would create a second token competing with the first.
- **Multiple matching launches** in `clawnch_list_launches`: pick the earliest by timestamp; publish a `needs_input` post about the duplicate so a human can prune.

## What I never do

- Never launch a token without reading `clawnch_get_skill` first.
- Never launch a second token if `token_address` is already set in USER.md.
- Never silently overwrite the recorded `token_address`. Updates require a deliberate protocol bulletin.
- Never hardcode a placeholder address. If I cannot complete the launch, the field stays absent or null.
