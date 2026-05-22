"""Bluesky AT Protocol MCP server for Blender agents.

Provides public-broadcast posting to Bluesky via the official AT Protocol XRPC
REST endpoints. Uses app passwords (no OAuth scopes, no review process):
generate one per agent at https://bsky.app/settings/app-passwords.

Free forever; Bluesky's API has no published pricing tier.

Env vars (per-agent, set via flyctl secrets):
    BLUESKY_HANDLE          e.g. "yield-aggregator.bsky.social" or a custom domain
    BLUESKY_APP_PASSWORD    app-specific password from the settings page

The MCP gracefully skips with a clear "credentials missing" status when either
env var is unset, so a partially-configured agent still boots clean.

Exposed tools:
    publish_post(text)          create a public post (max 300 chars on Bluesky)
    reply_to_post(uri, text)    reply in-thread
    read_notifications(limit)   recent notifications (mentions, replies, follows)
    delete_post(uri)            remove a post you created
    get_session_info()          diagnostic: confirm auth works
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:
    raise SystemExit("Missing 'mcp' package. Install: pip install mcp") from exc


PDS = os.environ.get("BLUESKY_PDS", "https://bsky.social")
HANDLE = os.environ.get("BLUESKY_HANDLE", "")
APP_PASSWORD = os.environ.get("BLUESKY_APP_PASSWORD", "")
USER_AGENT = "BlenderProtocol/0.1 (bluesky-mcp)"


_session: dict[str, Any] = {"jwt": None, "did": None, "handle": HANDLE, "refreshJwt": None}


def _http(method: str, path: str, body: dict | None = None, *, authed: bool = True) -> dict:
    url = f"{PDS}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json" if data else "application/x-www-form-urlencoded",
    }
    if authed and _session.get("jwt"):
        headers["Authorization"] = f"Bearer {_session['jwt']}"
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


def _login() -> dict:
    """Create or refresh a session. Idempotent on success."""
    if not HANDLE or not APP_PASSWORD:
        return {"error": "credentials_missing", "detail": "Set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD env vars."}
    resp = _http(
        "POST",
        "/xrpc/com.atproto.server.createSession",
        {"identifier": HANDLE, "password": APP_PASSWORD},
        authed=False,
    )
    if "error" in resp:
        return resp
    _session["jwt"] = resp.get("accessJwt")
    _session["refreshJwt"] = resp.get("refreshJwt")
    _session["did"] = resp.get("did")
    _session["handle"] = resp.get("handle", HANDLE)
    return {"ok": True, "did": resp.get("did"), "handle": resp.get("handle")}


def _ensure_session() -> dict | None:
    if not _session.get("jwt"):
        login = _login()
        if "error" in login:
            return login
    return None


mcp = FastMCP("bluesky")


@mcp.tool()
def get_session_info() -> dict[str, Any]:
    """Diagnostic: verify the agent can authenticate to Bluesky. Returns
    {ok: true, did, handle} on success or {error, detail} when credentials
    are missing or invalid. Safe to call at any time."""
    if not HANDLE or not APP_PASSWORD:
        return {"error": "credentials_missing", "handle_set": bool(HANDLE), "password_set": bool(APP_PASSWORD)}
    err = _ensure_session()
    if err:
        return err
    return {"ok": True, "did": _session["did"], "handle": _session["handle"], "pds": PDS}


@mcp.tool()
def publish_post(text: str) -> dict[str, Any]:
    """Create a public Bluesky post. Max 300 graphemes (Bluesky's hard limit).
    Returns the post URI and CID on success or an error dict. The agent's
    own DID is the author."""
    err = _ensure_session()
    if err:
        return err
    if len(text) > 300:
        return {"error": "post_too_long", "length": len(text), "max": 300}
    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    resp = _http(
        "POST",
        "/xrpc/com.atproto.repo.createRecord",
        {
            "repo": _session["did"],
            "collection": "app.bsky.feed.post",
            "record": record,
        },
    )
    if "error" in resp:
        return resp
    return {"ok": True, "uri": resp.get("uri"), "cid": resp.get("cid")}


@mcp.tool()
def reply_to_post(parent_uri: str, parent_cid: str, root_uri: str, root_cid: str, text: str) -> dict[str, Any]:
    """Reply in-thread. Caller must supply both parent and root references
    (Bluesky's thread model requires both). For a top-level reply, pass the
    same uri+cid as both parent and root.

    Max 300 graphemes."""
    err = _ensure_session()
    if err:
        return err
    if len(text) > 300:
        return {"error": "post_too_long", "length": len(text), "max": 300}
    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "reply": {
            "root": {"uri": root_uri, "cid": root_cid},
            "parent": {"uri": parent_uri, "cid": parent_cid},
        },
    }
    resp = _http(
        "POST",
        "/xrpc/com.atproto.repo.createRecord",
        {
            "repo": _session["did"],
            "collection": "app.bsky.feed.post",
            "record": record,
        },
    )
    if "error" in resp:
        return resp
    return {"ok": True, "uri": resp.get("uri"), "cid": resp.get("cid")}


@mcp.tool()
def read_notifications(limit: int = 25) -> dict[str, Any]:
    """Recent notifications: mentions, replies, likes, follows. Limit 1-100.
    The agent uses this to find conversations to engage with."""
    err = _ensure_session()
    if err:
        return err
    if limit < 1: limit = 1
    if limit > 100: limit = 100
    resp = _http("GET", f"/xrpc/app.bsky.notification.listNotifications?limit={limit}")
    if "error" in resp:
        return resp
    return {"ok": True, "notifications": resp.get("notifications", []), "cursor": resp.get("cursor")}


@mcp.tool()
def delete_post(uri: str) -> dict[str, Any]:
    """Delete one of your own posts by AT URI (e.g. at://did:plc:xyz/app.bsky.feed.post/abc123).
    Bluesky soft-deletes; the post is removed from the public feed but the
    DID's repo history retains a tombstone."""
    err = _ensure_session()
    if err:
        return err
    # AT URI format: at://<did>/<collection>/<rkey>
    parts = uri.replace("at://", "").split("/")
    if len(parts) != 3:
        return {"error": "invalid_uri", "expected": "at://did/collection/rkey"}
    repo, collection, rkey = parts
    if repo != _session["did"]:
        return {"error": "not_owner", "detail": "Can only delete posts in your own repo."}
    resp = _http(
        "POST",
        "/xrpc/com.atproto.repo.deleteRecord",
        {"repo": repo, "collection": collection, "rkey": rkey},
    )
    return resp if "error" in resp else {"ok": True, "uri": uri}


if __name__ == "__main__":
    mcp.run()
