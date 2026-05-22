"""Mastodon MCP server for Blender agents.

Lets the agent toot to its Mastodon account on any instance (mastodon.social,
fosstodon.org, indieweb.social, etc.). Federation means a post on one instance
is visible to followers on any other federated instance.

Free forever; Mastodon's API has no commercial tier.

Per-agent setup (one-time, manual operator step):
    1. Pick an instance and create an account at that instance.
    2. Go to Preferences -> Development -> New Application.
    3. Scopes needed: read, write. Submit.
    4. Copy the "Your access token" value.
    5. flyctl secrets set --app <agent-name>
         MASTODON_INSTANCE=https://<chosen-instance>
         MASTODON_ACCESS_TOKEN=<token>

Env vars:
    MASTODON_INSTANCE       full URL incl. https://, no trailing slash (default: https://mastodon.social)
    MASTODON_ACCESS_TOKEN   bearer token from app creation

The MCP gracefully skips with a clear error when MASTODON_ACCESS_TOKEN is unset.

Exposed tools:
    toot(text, visibility="public", spoiler_text="")     post a status
    reply_to_toot(parent_id, text, visibility="public")   reply in-thread
    read_notifications(limit=25)                          recent mentions/follows
    delete_toot(toot_id)                                  remove own status
    verify_credentials()                                  diagnostic
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:
    raise SystemExit("Missing 'mcp' package. Install: pip install mcp") from exc


INSTANCE = os.environ.get("MASTODON_INSTANCE", "https://mastodon.social").rstrip("/")
ACCESS_TOKEN = os.environ.get("MASTODON_ACCESS_TOKEN", "")
USER_AGENT = "BlenderProtocol/0.1 (mastodon-mcp)"


def _http(method: str, path: str, body: dict | None = None) -> dict:
    if not ACCESS_TOKEN:
        return {"error": "credentials_missing", "detail": "Set MASTODON_ACCESS_TOKEN env var."}
    url = f"{INSTANCE}{path}"
    data = urllib.parse.urlencode(body, doseq=True).encode("utf-8") if body else None
    headers = {
        "User-Agent": USER_AGENT,
        "Authorization": f"Bearer {ACCESS_TOKEN}",
    }
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
        except Exception:
            err_body = {"raw_status": e.code}
        return {"error": err_body, "http_status": e.code}
    except urllib.error.URLError as e:
        return {"error": f"network: {e}"}


mcp = FastMCP("mastodon")


@mcp.tool()
def verify_credentials() -> dict[str, Any]:
    """Diagnostic: confirms the access token authenticates against the
    configured instance. Returns the agent's Mastodon account record on
    success or an error dict."""
    if not ACCESS_TOKEN:
        return {"error": "credentials_missing"}
    resp = _http("GET", "/api/v1/accounts/verify_credentials")
    if "error" in resp:
        return resp
    return {
        "ok": True,
        "instance": INSTANCE,
        "id": resp.get("id"),
        "username": resp.get("username"),
        "acct": resp.get("acct"),
        "display_name": resp.get("display_name"),
        "followers_count": resp.get("followers_count"),
        "following_count": resp.get("following_count"),
        "statuses_count": resp.get("statuses_count"),
    }


@mcp.tool()
def toot(text: str, visibility: str = "public", spoiler_text: str = "") -> dict[str, Any]:
    """Post a Mastodon status (toot). Max 500 chars on most instances.

    visibility: 'public' | 'unlisted' | 'private' (followers-only) | 'direct'
    spoiler_text: optional content warning shown before the body

    Returns the new status record or an error dict."""
    if visibility not in ("public", "unlisted", "private", "direct"):
        return {"error": "invalid_visibility", "got": visibility}
    if len(text) > 500:
        return {"error": "post_too_long", "length": len(text), "max": 500}
    body: dict[str, Any] = {"status": text, "visibility": visibility}
    if spoiler_text:
        body["spoiler_text"] = spoiler_text
    resp = _http("POST", "/api/v1/statuses", body)
    if "error" in resp:
        return resp
    return {"ok": True, "id": resp.get("id"), "url": resp.get("url"), "uri": resp.get("uri")}


@mcp.tool()
def reply_to_toot(parent_id: str, text: str, visibility: str = "public") -> dict[str, Any]:
    """Reply to an existing toot in-thread by its numeric id.

    visibility defaults to public. Visibility of a reply cannot be MORE
    public than the parent."""
    if visibility not in ("public", "unlisted", "private", "direct"):
        return {"error": "invalid_visibility", "got": visibility}
    if len(text) > 500:
        return {"error": "post_too_long", "length": len(text), "max": 500}
    resp = _http("POST", "/api/v1/statuses", {
        "status": text,
        "in_reply_to_id": parent_id,
        "visibility": visibility,
    })
    if "error" in resp:
        return resp
    return {"ok": True, "id": resp.get("id"), "url": resp.get("url")}


@mcp.tool()
def read_notifications(limit: int = 25) -> dict[str, Any]:
    """Recent notifications: mentions, follows, reblogs, favourites.
    Mastodon's API caps limit at 30."""
    if limit < 1: limit = 1
    if limit > 30: limit = 30
    resp = _http("GET", f"/api/v1/notifications?limit={limit}")
    if isinstance(resp, dict) and "error" in resp:
        return resp
    return {"ok": True, "notifications": resp if isinstance(resp, list) else []}


@mcp.tool()
def delete_toot(toot_id: str) -> dict[str, Any]:
    """Delete one of your own toots by id. Mastodon returns the deleted
    status with its text included so the caller can salvage if needed."""
    resp = _http("DELETE", f"/api/v1/statuses/{toot_id}")
    if isinstance(resp, dict) and "error" in resp:
        return resp
    return {"ok": True, "deleted_id": toot_id}


if __name__ == "__main__":
    mcp.run()
