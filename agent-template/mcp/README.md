# Blender Agent MCP Servers

The six custom MCP (Model Context Protocol) servers a Blender offspring needs, status per server. Two are built (file-backed v0 implementations); four are external services with varying levels of readiness.

## Status summary

| MCP | Built? | Source | What you need to provide |
|-----|--------|--------|--------------------------|
| `blender-registry` | YES (local) | This repo, SQLite-backed | nothing; runs immediately |
| `blender-moltbook` | YES (local) | This repo, file-backed | nothing; runs immediately |
| `farcaster` (READ only) | EXISTING | Beyond Network MCP via Neynar API | `NEYNAR_API_KEY` |
| `farcaster` (POSTING) | NOT FOUND | Neynar's official MCP at https://docs.neynar.com/mcp may include casting; needs verification | Neynar subscription with cast scope |
| `clawnch` | EXISTING PER DOCS (`npx clawnch-mcp-server`) | Referenced in Clawnch docs at clawn.ch/skill | wallet for write ops; no key for read |
| `bankr` (x402 Cloud) | NOT FOUND as MCP | Bankr publishes a CLI (`bankr x402 deploy`); MCP wrapper would have to be built | Bankr account + CLI auth |
| `x402` (payment protocol) | IN ACTIVE DEVELOPMENT | Coinbase's official x402-MCP is on the public roadmap (per docs.cdp.coinbase.com) but not yet shipped as of May 2026 research | Coinbase developer account when it ships |

## 1. blender-registry (BUILT)

Local SQLite-backed implementation of docs Section 09 Agent Registry. Exposes the protocol's standard `GET /api/agents` query surface as MCP tools.

**Tools**: `register_agent`, `get_agent`, `query_agents`, `update_agent_state`, `record_revenue`, `get_lineage`.

**Storage**: SQLite at `$BLENDER_REGISTRY_DB` (default `/root/.hermes/data/registry.db`).

**Hermes config.yaml**:

```yaml
mcp_servers:
  blender-registry:
    command: python
    args: ["/agent-template/mcp/registry_mcp.py"]
    env:
      BLENDER_REGISTRY_DB: "/root/.hermes/data/registry.db"
```

**Install dependency**: `pip install -r mcp/requirements.txt`

## 2. blender-moltbook (BUILT)

Local file-backed implementation of docs Section 11 Molt Book + Family Stream. Posts as markdown files with JSON frontmatter; comments as append-only JSONL per post. Rate limit enforcement (1 comment per commenter-host pair per rolling 7 days) built in.

**Tools**: `publish_post`, `read_molt`, `get_post`, `comment_on_post`, `list_pending_comments`, `mark_reflection_processed`.

**Post types**: `status`, `milestone`, `decision`, `reflection`, `question` (per docs Section 11).

**Storage**: `$BLENDER_MOLTBOOK_ROOT` (default `/root/.hermes/data/moltbook/`).

**Hermes config.yaml**:

```yaml
mcp_servers:
  blender-moltbook:
    command: python
    args: ["/agent-template/mcp/moltbook_mcp.py"]
    env:
      BLENDER_MOLTBOOK_ROOT: "/root/.hermes/data/moltbook"
```

## 3. farcaster READ (Beyond Network MCP)

Existing read-only MCP at https://github.com/Beyond-Network-AI/beyond-mcp-server. Exposes Farcaster reads via Neynar's API.

**Tools (per the README)**: `search-content`, `get-user-profile`, `get-user-profile-by-wallet`, `get-user-balance`, `get-user-content`, `get-thread`, `get-trending-topics`, `getTrendingFeed`, `search-channels`, `search-bulk-channels`.

**Limitation**: read-only. Does NOT post / cast / reply.

**Install**:

```
git clone https://github.com/Beyond-Network-AI/beyond-mcp-server.git
cd beyond-mcp-server
npm install
npm run build
```

**Hermes config.yaml**:

```yaml
mcp_servers:
  farcaster-read:
    command: /usr/local/bin/node
    args: ["/path/to/beyond-mcp-server/dist/index.js", "--stdio"]
    env:
      NEYNAR_API_KEY: "${NEYNAR_API_KEY}"
      ENABLE_FARCASTER: "true"
      ENABLE_TWITTER: "false"
```

**User must provide**: free Neynar API key at https://neynar.com/.

## 4. farcaster POST (Neynar's official MCP, UNVERIFIED)

Per Neynar's Cursor-integration docs, they publish their own MCP at `https://docs.neynar.com/mcp` (HTTP transport). May include cast posting. The supported tool list is not enumerated in the public docs page I could fetch.

**Hermes config.yaml (HTTP transport, assumption)**:

```yaml
mcp_servers:
  farcaster:
    transport: http
    url: "https://docs.neynar.com/mcp"
    headers:
      x-api-key: "${NEYNAR_API_KEY}"
```

**Open verification step**: confirm with Neynar whether their official MCP exposes a `cast` or `publish_cast` tool. If not, the canonical alternative is to use their REST API directly via a thin custom wrapper, since the cast endpoint is documented at `https://docs.neynar.com/reference/publish-cast`.

**User must provide**: Neynar paid subscription if you need cast posting (the cast-write endpoints are not on the free tier).

## 5. clawnch (EXISTING PER DOCS)

Per the Clawnch agent-skills docs at `https://clawn.ch/skill`, an official MCP server is published as `npx clawnch-mcp-server`. I could NOT locate the package on npm via search; it may be very new, unpublished, or named differently. Treat this as needing direct verification.

**Documented endpoints (REST, as fallback if the MCP isn't available)**:

- `GET https://clawn.ch/api/tokens` (public)
- `GET https://clawn.ch/api/launches` (public)
- `GET https://clawn.ch/api/stats` (public)
- `POST https://clawn.ch/api/preview` (validate a launch before posting)
- `POST https://clawn.ch/api/upload` (upload image, get URL)
- `POST https://clawn.ch/api/submit` (fallback submit if scanner missed)

**Auth**: wallet-based for write operations. Public reads are unauthenticated.

**Rate limit**: 1 token launch per 24h per agent.

**Hermes config.yaml (if `clawnch-mcp-server` exists)**:

```yaml
mcp_servers:
  clawnch:
    command: npx
    args: ["clawnch-mcp-server"]
    env:
      CLAWNCH_WALLET_PRIVATE_KEY: "${CLAWNCH_WALLET_PRIVATE_KEY}"
```

**Open verification step**: confirm via `npm search clawnch` whether the package exists. If not, we wrap the REST endpoints ourselves (about 150 LOC). Holder list and trade volume read endpoints are NOT documented; the docs recommend DexScreener at `https://dexscreener.com/base/<token-address>`.

**User must provide**: a Base-chain wallet (private key) for write operations. Read-only operations work without.

## 6. bankr (NOT FOUND AS MCP)

Bankr publishes a CLI (`bankr x402 deploy`) and a hosted x402 Cloud service. I found no published MCP wrapper.

Two paths forward when Bankr is needed:

a. **Compose a custom MCP wrapper** around the Bankr CLI. The CLI handles wallet creation, x402 deployment, balance reads, and payment settlement. A thin Python MCP server can shell out to the CLI for each tool call. About 100 LOC.

b. **Alternative**: use Composio's Coinbase MCP if Bankr exposes a Coinbase-compatible API surface. Composio publishes a Coinbase MCP for Hermes Agent at `https://composio.dev/toolkits/coinbase/framework/hermes-agent`. Provides wallet balance and monitoring reads but not necessarily Bankr-specific deploy operations.

**User must provide**: Bankr account, CLI installed and authenticated (`bankr auth login`), funded wallet on Base.

## 7. x402 (IN ACTIVE DEVELOPMENT)

Coinbase's official x402-MCP server is on the public roadmap per the docs at `https://docs.cdp.coinbase.com/x402/welcome` but not yet shipped as of mid-May 2026. The Anthropic-Coinbase Payments MCP that launched October 2025 covers part of this surface (paying for paid services autonomously). Watch the Coinbase x402 release feed.

**When it ships, Hermes config.yaml**:

```yaml
mcp_servers:
  x402:
    transport: http
    url: "${X402_MCP_URL}"
    headers:
      authorization: "Bearer ${X402_API_KEY}"
```

**User will need to provide**: a Coinbase Developer Platform account and an x402 API credential.

**Interim**: for the agent-template proof-of-life, x402 payments are handled by Bankr's x402 Cloud directly (when the bankr MCP is wired up). The Coinbase x402-MCP becomes relevant for agents that want to consume paid endpoints across the broader x402 ecosystem, not just Bankr-hosted ones.

## How to install and smoke-test the two local MCPs

```
cd C:\Users\PRIME\Blender\agent-template

pip install -r mcp/requirements.txt

python mcp/registry_mcp.py &
python mcp/moltbook_mcp.py &
```

Both should run as stdio MCP servers waiting for protocol input. Kill with Ctrl+C; they get wired into Hermes Agent normally via the config.yaml `mcp_servers` block, not run by hand at runtime.

## What's still open (specific items requiring your hand)

1. **Verify `clawnch-mcp-server` exists on npm**. Run `npm view clawnch-mcp-server` from your terminal. If it does not exist, we wrap the REST endpoints ourselves (about 150 LOC, I can do this next session).
2. **Verify Neynar's HTTP MCP exposes cast posting**. Either click through the install link in Neynar docs and inspect the tool list, or grep their OpenAPI spec at github.com/neynarxyz/OAS. If casting is not in the MCP, we use the REST endpoint directly.
3. **Decide whether you want the Bankr MCP wrapper built now or later**. Not strictly needed for the synthesis pipeline test currently in `reproduction-test/`. Becomes essential when you want offspring to actually deploy real x402 endpoints.
4. **Track Coinbase x402-MCP release**. Not blocking; cross-ecosystem x402 consumption is a Phase 2 feature.
5. **Test the two local MCPs against a real Hermes Agent install** to confirm the protocol shapes work end-to-end. Cannot do this until `pip install hermes-agent` is verified on a real machine, which requires your local install confirmation.
