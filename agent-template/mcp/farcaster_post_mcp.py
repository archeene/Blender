"""
Farcaster posting MCP server (Neynar API wrapper).

Beyond Network's MCP exposes Farcaster READS via Neynar. This server wraps
Neynar's REST API for WRITES (publish cast, reply, read mentions, delete).

Required env:
  NEYNAR_API_KEY      Your Neynar API key (https://neynar.com/)
  NEYNAR_SIGNER_UUID  Signer UUID for the Farcaster account this agent
                      posts as. Provision via Neynar dashboard or their
                      managed signer flow.

Tools exposed:
  - publish_cast(text, channel_id=None, parent_cast_hash=None, embeds=None)
  - reply_to_cast(parent_hash, text, embeds=None)
  - read_mentions(fid=None, limit=25)
  - delete_cast(cast_hash)

Wire into Hermes Agent config.yaml:
    mcp_servers:
      farcaster-post:
        command: python
        args: ["/agent-template/mcp/farcaster_post_mcp.py"]
        env:
          NEYNAR_API_KEY: "${NEYNAR_API_KEY}"
          NEYNAR_SIGNER_UUID: "${NEYNAR_SIGNER_UUID}"

Stdlib only (urllib.request, json, os). MCP SDK required (pip install mcp).
"""
import json
import os
import urllib.error
import urllib.request
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:
    raise SystemExit(
        "Missing 'mcp' package. Install with: pip install mcp"
    ) from exc


NEYNAR_BASE = os.environ.get("NEYNAR_BASE_URL", "https://api.neynar.com/v2/farcaster")
API_KEY = os.environ.get("NEYNAR_API_KEY", "")
SIGNER_UUID = os.environ.get("NEYNAR_SIGNER_UUID", "")

mcp = FastMCP("farcaster-post")


def _request(method: str, path: str, body: dict | None = None, params: dict | None = None) -> dict[str, Any]:
    """Low-level HTTP wrapper. Returns parsed JSON or {'error': ...} dict."""
    if not API_KEY:
        return {"error": "NEYNAR_API_KEY env var not set; cannot call Neynar API."}

    url = f"{NEYNAR_BASE.rstrip('/')}/{path.lstrip('/')}"
    if params:
        from urllib.parse import urlencode
        url = f"{url}?{urlencode({k: v for k, v in params.items() if v is not None})}"

    headers = {
        "x-api-key": API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {"ok": True}
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return {
            "error": f"HTTP {e.code} from Neynar",
            "code": e.code,
            "url": url,
            "body": err_body[:1000],
        }
    except urllib.error.URLError as e:
        return {"error": f"URL error: {e}", "url": url}
    except json.JSONDecodeError as e:
        return {"error": f"non-JSON response: {e}", "url": url}


@mcp.tool()
def publish_cast(
    text: str,
    channel_id: str | None = None,
    parent_cast_hash: str | None = None,
    embeds: list[dict] | None = None,
) -> dict[str, Any]:
    """Publish a cast to Farcaster as the agent's configured Farcaster account.

    text: cast body, up to 320 chars per Farcaster spec
    channel_id: optional channel id (e.g. 'crypto', 'ai-agents'); cast goes to channel
    parent_cast_hash: optional parent cast hash if this is a reply
    embeds: optional list of {url} or {cast_id: {fid, hash}} dicts for attachments

    Returns the cast record from Neynar including the new cast hash.
    """
    if not SIGNER_UUID:
        return {"error": "NEYNAR_SIGNER_UUID env var not set; cannot post."}
    if len(text) > 320:
        return {"error": f"cast text too long ({len(text)} chars; max 320)"}

    body: dict[str, Any] = {"signer_uuid": SIGNER_UUID, "text": text}
    if channel_id:
        body["channel_id"] = channel_id
    if parent_cast_hash:
        body["parent"] = parent_cast_hash
    if embeds:
        body["embeds"] = embeds

    return _request("POST", "/cast", body=body)


@mcp.tool()
def reply_to_cast(
    parent_hash: str,
    text: str,
    embeds: list[dict] | None = None,
) -> dict[str, Any]:
    """Reply to an existing cast.

    parent_hash: the hash of the cast to reply to
    text: reply body, up to 320 chars
    """
    return publish_cast(
        text=text, parent_cast_hash=parent_hash, embeds=embeds
    )


@mcp.tool()
def read_mentions(fid: int | None = None, limit: int = 25) -> dict[str, Any]:
    """Read recent mentions of the agent's Farcaster account.

    fid: Farcaster ID to query mentions for. If None, uses the agent's own
         configured FID (which requires the agent to know its FID; for now
         the caller must supply explicitly).
    limit: max number of mentions to return (Neynar caps at 100).
    """
    if fid is None:
        return {
            "error": "fid required. Pass the agent's Farcaster ID. "
            "(Agent should know its own FID from when its account was provisioned.)"
        }
    return _request(
        "GET",
        "/feed/user/replies_and_recasts",
        params={"fid": fid, "limit": min(limit, 100)},
    )


@mcp.tool()
def delete_cast(cast_hash: str) -> dict[str, Any]:
    """Delete a previously published cast. Caller must have published it
    (the signer_uuid must match the cast's author).
    """
    if not SIGNER_UUID:
        return {"error": "NEYNAR_SIGNER_UUID env var not set; cannot delete."}
    return _request(
        "DELETE",
        "/cast",
        body={"signer_uuid": SIGNER_UUID, "target_hash": cast_hash},
    )


if __name__ == "__main__":
    mcp.run()
