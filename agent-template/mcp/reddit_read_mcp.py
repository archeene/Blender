"""Reddit read-only MCP for Blender agents (signal ingestion only).

Reddit's culture is hostile to bot writes (auto-removal, shadowbans,
karma-gated subs). This MCP is intentionally READ-ONLY: the agent uses
Reddit as an input signal source for niche discussions, then publishes
its own analysis to friendlier surfaces (Bluesky / Mastodon / Nostr /
Moltbook).

Uses Reddit's public .json endpoints which require no OAuth and no signup.
Reddit's rate limit for unauthenticated reads is generous (~60 req/min)
and respects a clear User-Agent string per their API rules.

No env vars required. The MCP works the moment the agent boots.

Per Reddit's ToS, the User-Agent string identifies the bot and the agent
contact. Per-agent customization happens via REDDIT_USER_AGENT env var
(optional; defaults to a generic Blender protocol identifier).

Exposed tools:
    search_subreddit(subreddit, query, limit, sort, time_filter)
    read_top(subreddit, limit, time_filter)
    read_new(subreddit, limit)
    read_hot(subreddit, limit)
    read_comments(post_id, subreddit, limit, sort)
    search_all(query, limit, sort)
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


DEFAULT_USER_AGENT = (
    "BlenderProtocol-read/0.1 (by /u/blender-protocol; "
    "contact: https://blenderai.link; signal-ingestion-only, no writes)"
)
USER_AGENT = os.environ.get("REDDIT_USER_AGENT", DEFAULT_USER_AGENT)
BASE = "https://www.reddit.com"


def _get(path: str, params: dict | None = None) -> dict | list:
    q = ("?" + urllib.parse.urlencode(params)) if params else ""
    url = f"{BASE}{path}.json{q}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:
            body = {"raw_status": e.code}
        return {"error": body, "http_status": e.code}
    except urllib.error.URLError as e:
        return {"error": f"network: {e}"}


def _flatten_listing(resp: Any) -> list[dict]:
    """Reddit's listings are nested; extract just the post data dicts."""
    if not isinstance(resp, dict):
        return []
    children = resp.get("data", {}).get("children", [])
    out = []
    for c in children:
        d = c.get("data", {})
        out.append({
            "id": d.get("id"),
            "title": d.get("title"),
            "selftext": (d.get("selftext") or "")[:2000],
            "url": d.get("url"),
            "permalink": f"https://reddit.com{d.get('permalink', '')}",
            "subreddit": d.get("subreddit"),
            "author": d.get("author"),
            "score": d.get("score"),
            "num_comments": d.get("num_comments"),
            "upvote_ratio": d.get("upvote_ratio"),
            "created_utc": d.get("created_utc"),
            "is_self": d.get("is_self"),
            "over_18": d.get("over_18"),
        })
    return out


mcp = FastMCP("reddit-read")


@mcp.tool()
def search_subreddit(
    subreddit: str,
    query: str,
    limit: int = 25,
    sort: str = "relevance",
    time_filter: str = "month",
) -> dict[str, Any]:
    """Search posts within a specific subreddit.

    sort: 'relevance' | 'hot' | 'top' | 'new' | 'comments'
    time_filter: 'hour' | 'day' | 'week' | 'month' | 'year' | 'all'
    """
    if limit < 1: limit = 1
    if limit > 100: limit = 100
    resp = _get(f"/r/{subreddit}/search", {
        "q": query,
        "restrict_sr": "1",
        "sort": sort,
        "t": time_filter,
        "limit": limit,
    })
    if isinstance(resp, dict) and "error" in resp:
        return resp
    return {"ok": True, "subreddit": subreddit, "query": query, "posts": _flatten_listing(resp)}


@mcp.tool()
def read_top(subreddit: str, limit: int = 25, time_filter: str = "day") -> dict[str, Any]:
    """Top posts in a subreddit. time_filter: hour/day/week/month/year/all."""
    if limit < 1: limit = 1
    if limit > 100: limit = 100
    resp = _get(f"/r/{subreddit}/top", {"t": time_filter, "limit": limit})
    if isinstance(resp, dict) and "error" in resp:
        return resp
    return {"ok": True, "subreddit": subreddit, "posts": _flatten_listing(resp)}


@mcp.tool()
def read_new(subreddit: str, limit: int = 25) -> dict[str, Any]:
    """Newest posts in a subreddit (most recent first)."""
    if limit < 1: limit = 1
    if limit > 100: limit = 100
    resp = _get(f"/r/{subreddit}/new", {"limit": limit})
    if isinstance(resp, dict) and "error" in resp:
        return resp
    return {"ok": True, "subreddit": subreddit, "posts": _flatten_listing(resp)}


@mcp.tool()
def read_hot(subreddit: str, limit: int = 25) -> dict[str, Any]:
    """Trending posts in a subreddit (Reddit's blended ranking)."""
    if limit < 1: limit = 1
    if limit > 100: limit = 100
    resp = _get(f"/r/{subreddit}/hot", {"limit": limit})
    if isinstance(resp, dict) and "error" in resp:
        return resp
    return {"ok": True, "subreddit": subreddit, "posts": _flatten_listing(resp)}


@mcp.tool()
def read_comments(subreddit: str, post_id: str, limit: int = 50, sort: str = "top") -> dict[str, Any]:
    """Fetch comments on a specific post. sort: 'top' | 'best' | 'new' | 'controversial'."""
    if limit < 1: limit = 1
    if limit > 500: limit = 500
    resp = _get(f"/r/{subreddit}/comments/{post_id}", {"limit": limit, "sort": sort})
    if isinstance(resp, dict) and "error" in resp:
        return resp
    if not isinstance(resp, list) or len(resp) < 2:
        return {"ok": True, "post_id": post_id, "comments": []}
    comments_listing = resp[1].get("data", {}).get("children", [])
    out = []
    for c in comments_listing:
        d = c.get("data", {})
        out.append({
            "id": d.get("id"),
            "author": d.get("author"),
            "body": (d.get("body") or "")[:2000],
            "score": d.get("score"),
            "created_utc": d.get("created_utc"),
            "depth": d.get("depth"),
        })
    return {"ok": True, "post_id": post_id, "comments": out}


@mcp.tool()
def search_all(query: str, limit: int = 25, sort: str = "relevance") -> dict[str, Any]:
    """Cross-subreddit search. Useful when the agent doesn't yet know which
    subreddit contains the signal it's looking for."""
    if limit < 1: limit = 1
    if limit > 100: limit = 100
    resp = _get("/search", {"q": query, "sort": sort, "limit": limit})
    if isinstance(resp, dict) and "error" in resp:
        return resp
    return {"ok": True, "query": query, "posts": _flatten_listing(resp)}


if __name__ == "__main__":
    mcp.run()
