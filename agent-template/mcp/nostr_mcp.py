"""Nostr MCP for Blender agents.

Nostr is fully decentralized: no signup, no API key. Each agent has a
secp256k1 keypair (private = nsec, public = npub) and publishes signed
events to one or more public relays. Posts are visible to anyone on any
client that follows the npub.

Per-agent keypair lifecycle:
    First boot: entrypoint.sh calls this MCP's `ensure_identity` tool
    (or runs `python nostr_mcp.py --init`) to generate and persist the
    keypair under $NOSTR_KEY_DIR (default /opt/data/.nostr/). Subsequent
    boots reuse the persisted key. npub becomes the agent's public Nostr
    identity for life.

Implementation status (current state):
    Stage 1 (this file): keypair generation + storage + tool surface. Actual
    relay posting requires the `coincurve` (Schnorr signing) and `websockets`
    pip packages. If they aren't installed, the publish tools return a clear
    error and the agent stays alive — same graceful-skip pattern as the other
    optional MCPs in this directory.

    Stage 2 (post-install): once `pip install coincurve websockets` runs in
    the Dockerfile (or via requirements.txt), publishing activates with no
    code change in this file.

Env vars:
    NOSTR_KEY_DIR       where to store the keypair (default /opt/data/.nostr)
    NOSTR_RELAYS        comma-separated relay WS URLs (default: relay.damus.io,
                        nos.lol, relay.nostr.band — broad popular relays)

Exposed tools:
    ensure_identity()                       generate or load the keypair
    get_npub()                              return the agent's public Nostr identity
    publish_note(text)                      publish a NIP-01 kind:1 text note
    reply_to_note(parent_id, text)          publish a NIP-01 kind:1 reply
    read_relay_status()                     diagnostic: which relays we can reach
"""
import hashlib
import json
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:
    raise SystemExit("Missing 'mcp' package. Install: pip install mcp") from exc


KEY_DIR = Path(os.environ.get("NOSTR_KEY_DIR", "/opt/data/.nostr"))
RELAYS = [r.strip() for r in os.environ.get(
    "NOSTR_RELAYS",
    "wss://relay.damus.io,wss://nos.lol,wss://relay.nostr.band"
).split(",") if r.strip()]

KEY_DIR.mkdir(parents=True, exist_ok=True)
PRIV_PATH = KEY_DIR / "nsec.hex"
PUB_PATH = KEY_DIR / "npub.hex"


# ----------------------------------------------------------------------------
# Keypair management — stdlib only. Uses secp256k1 curve order via PyCA's
# cryptography is unavailable here, so for now we just generate the 32-byte
# private key. Deriving the public key requires secp256k1 EC math (the
# `coincurve` pip package) and is done lazily inside _derive_pubkey when
# coincurve is importable. Without coincurve, the keypair file holds only the
# private scalar; pubkey derivation surfaces a clear error.
# ----------------------------------------------------------------------------


def _generate_private_key() -> str:
    """secp256k1 private keys are 32-byte ints in [1, curve_order - 1].
    We use stdlib `secrets.randbits` and reject zero (vanishingly rare)."""
    while True:
        k = secrets.token_bytes(32)
        if any(b != 0 for b in k):
            return k.hex()


def _derive_pubkey(privkey_hex: str) -> str | None:
    """Try to derive the secp256k1 x-only pubkey (NIP-01 / BIP-340) from a
    private key. Returns None if the `coincurve` package isn't installed —
    caller must surface that to the user."""
    try:
        from coincurve import PrivateKey  # type: ignore
    except ImportError:
        return None
    sk = PrivateKey(bytes.fromhex(privkey_hex))
    # NIP-01 uses x-only pubkeys (BIP-340 / Schnorr). coincurve returns the
    # compressed 33-byte form (0x02/0x03 prefix + 32-byte X); strip the prefix.
    compressed = sk.public_key.format(compressed=True)
    return compressed[1:].hex()  # 32-byte x-coordinate


def _load_or_create_identity() -> dict[str, Any]:
    """Return {"privkey": hex, "pubkey": hex_or_none, "created_at": iso}.
    Idempotent: subsequent calls reload the saved key."""
    if PRIV_PATH.exists():
        privkey = PRIV_PATH.read_text(encoding="utf-8").strip()
    else:
        privkey = _generate_private_key()
        PRIV_PATH.write_text(privkey, encoding="utf-8")
        # Permissions: best-effort 0600. On Windows-mounted volumes this
        # may be a no-op which is fine for the test bench.
        try:
            os.chmod(PRIV_PATH, 0o600)
        except OSError:
            pass

    pubkey = _derive_pubkey(privkey)
    if pubkey:
        PUB_PATH.write_text(pubkey, encoding="utf-8")
    elif PUB_PATH.exists():
        pubkey = PUB_PATH.read_text(encoding="utf-8").strip()

    return {
        "privkey_hex": privkey,
        "pubkey_hex": pubkey,
        "key_dir": str(KEY_DIR),
        "created_at_unix": int(PRIV_PATH.stat().st_ctime) if PRIV_PATH.exists() else None,
    }


def _sign_event(privkey_hex: str, event_id_hex: str) -> str | None:
    """BIP-340 Schnorr signature over the 32-byte event id. Returns hex sig
    or None if coincurve unavailable."""
    try:
        from coincurve import PrivateKey  # type: ignore
    except ImportError:
        return None
    sk = PrivateKey(bytes.fromhex(privkey_hex))
    sig = sk.sign_schnorr(bytes.fromhex(event_id_hex))
    return sig.hex()


def _event_id(pubkey_hex: str, created_at: int, kind: int, tags: list, content: str) -> str:
    """NIP-01: event id = SHA256(canonical JSON of [0, pubkey, created_at, kind, tags, content])."""
    payload = [0, pubkey_hex, created_at, kind, tags, content]
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _build_event(privkey: str, pubkey: str, kind: int, content: str, tags: list | None = None) -> dict | None:
    """Build a signed NIP-01 event. Returns None if signing is unavailable."""
    tags = tags or []
    created_at = int(time.time())
    eid = _event_id(pubkey, created_at, kind, tags, content)
    sig = _sign_event(privkey, eid)
    if sig is None:
        return None
    return {
        "id": eid,
        "pubkey": pubkey,
        "created_at": created_at,
        "kind": kind,
        "tags": tags,
        "content": content,
        "sig": sig,
    }


def _broadcast(event: dict) -> dict[str, Any]:
    """Publish to all configured relays via WebSocket. Returns per-relay
    accept/reject status. Requires the `websockets` package."""
    try:
        import asyncio
        from websockets.sync.client import connect  # type: ignore
    except ImportError:
        return {"error": "websockets_missing", "detail": "pip install websockets to activate Nostr publishing."}

    results: dict[str, str] = {}
    payload = json.dumps(["EVENT", event])
    for relay in RELAYS:
        try:
            with connect(relay, open_timeout=8, close_timeout=4) as ws:
                ws.send(payload)
                # NIP-20: relay replies with ["OK", <event-id>, <true|false>, <message>]
                resp = ws.recv(timeout=8)
                results[relay] = resp[:300]
        except Exception as e:
            results[relay] = f"error: {type(e).__name__}: {e}"
    return results


# ----------------------------------------------------------------------------
# MCP tool surface
# ----------------------------------------------------------------------------

mcp = FastMCP("nostr")


@mcp.tool()
def ensure_identity() -> dict[str, Any]:
    """Generate (or load) this agent's Nostr keypair. Idempotent. Persists
    the private key under $NOSTR_KEY_DIR for life. Returns {pubkey_hex,
    coincurve_available: bool, key_dir} so the agent knows its public
    identity and whether posting is functional yet."""
    ident = _load_or_create_identity()
    return {
        "ok": True,
        "pubkey_hex": ident.get("pubkey_hex"),
        "coincurve_available": ident.get("pubkey_hex") is not None,
        "key_dir": ident.get("key_dir"),
        "relays_configured": len(RELAYS),
        "note": (
            "Private key generated and persisted. "
            + ("Schnorr signing available; publish_note will work."
               if ident.get("pubkey_hex")
               else "coincurve not installed; publish_note will return an error until 'pip install coincurve websockets' lands in the Docker image.")
        ),
    }


@mcp.tool()
def get_npub() -> dict[str, Any]:
    """Return the agent's public Nostr identity (x-only hex pubkey). For
    human-readable bech32 npub, third-party clients render this hex
    as npub1..."""
    ident = _load_or_create_identity()
    if not ident.get("pubkey_hex"):
        return {"error": "pubkey_not_derived", "reason": "coincurve not installed"}
    return {"ok": True, "pubkey_hex": ident["pubkey_hex"], "key_dir": ident["key_dir"]}


@mcp.tool()
def publish_note(text: str, tags: list[list[str]] | None = None) -> dict[str, Any]:
    """Publish a NIP-01 kind:1 text note to all configured relays. tags is
    an optional list of NIP-12 tag arrays (e.g. [["t","blender"], ["p", "<pubkey>"]]).
    Returns per-relay broadcast results."""
    ident = _load_or_create_identity()
    privkey = ident.get("privkey_hex")
    pubkey = ident.get("pubkey_hex")
    if not pubkey:
        return {"error": "signing_unavailable", "detail": "coincurve not installed in this environment."}

    event = _build_event(privkey, pubkey, kind=1, content=text, tags=tags or [])
    if event is None:
        return {"error": "build_failed"}
    results = _broadcast(event)
    if isinstance(results, dict) and "error" in results:
        return results
    return {"ok": True, "event_id": event["id"], "relays": results}


@mcp.tool()
def reply_to_note(parent_event_id: str, parent_author_pubkey: str, text: str) -> dict[str, Any]:
    """Publish a reply (NIP-01 kind:1 with "e" + "p" tags pointing at the
    parent). The agent uses this to engage with mentions and conversations."""
    tags = [
        ["e", parent_event_id, "", "reply"],
        ["p", parent_author_pubkey],
    ]
    return publish_note(text, tags=tags)


@mcp.tool()
def read_relay_status() -> dict[str, Any]:
    """Diagnostic: try to open a WebSocket to each configured relay.
    Returns per-relay reachability so the operator can prune dead relays."""
    try:
        from websockets.sync.client import connect  # type: ignore
    except ImportError:
        return {"error": "websockets_missing", "relays_configured": RELAYS}
    out: dict[str, str] = {}
    for relay in RELAYS:
        try:
            with connect(relay, open_timeout=5, close_timeout=2):
                out[relay] = "reachable"
        except Exception as e:
            out[relay] = f"unreachable: {type(e).__name__}"
    return {"ok": True, "relays": out}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--init":
        # Standalone keypair init for entrypoint.sh, no MCP needed.
        ident = _load_or_create_identity()
        print(json.dumps({
            "pubkey_hex": ident.get("pubkey_hex"),
            "coincurve_available": ident.get("pubkey_hex") is not None,
            "key_dir": ident.get("key_dir"),
        }, indent=2))
        sys.exit(0)
    mcp.run()
