"""One-shot: mint a trade-only Hyperliquid AGENT wallet for trendpilot.

RUN THIS LOCALLY on your own machine, with your MASTER wallet key. The master
key NEVER goes to the server. This produces a trade-only AGENT key (it can
place/cancel orders but CANNOT withdraw funds) that you then set as the Fly
secret HYPERLIQUID_AGENT_KEY.

Do testnet first:
    pip install hyperliquid-python-sdk eth-account
    # get testnet USDC from the Hyperliquid testnet faucet first
    set HL_MASTER_KEY=0x...        # your master wallet private key (PowerShell: $env:HL_MASTER_KEY)
    set HL_NETWORK=testnet         # or mainnet, later
    python approve_agent.py

Then:
    flyctl secrets set --app blender-trendpilot \
        HYPERLIQUID_AGENT_KEY=<printed agent key> \
        HYPERLIQUID_MASTER_ADDRESS=<printed master address>

Security:
  - HL_MASTER_KEY is read from env, never printed, never written to disk.
  - The AGENT key is printed once. Copy it into the Fly secret, then clear
    your shell history (PowerShell: Clear-History; and delete the console
    history file if persisted).
  - The agent key cannot withdraw. Worst case if it leaks = bad trades up to
    the deposited balance, never a drain.
"""
import os
import sys

try:
    from hyperliquid.exchange import Exchange
    from hyperliquid.utils import constants
    from eth_account import Account
except ImportError:
    sys.exit("Missing deps. Run: pip install hyperliquid-python-sdk eth-account")

master_key = os.environ.get("HL_MASTER_KEY")
if not master_key:
    sys.exit("Set HL_MASTER_KEY to your master wallet private key (0x...).")

network = os.environ.get("HL_NETWORK", "testnet").lower()
base = constants.MAINNET_API_URL if network == "mainnet" else constants.TESTNET_API_URL

master = Account.from_key(master_key)
print(f"Master address: {master.address}")
print(f"Network:        {network}")
print(f"API base:       {base}")
print()

ex = Exchange(master, base)
ret = ex.approve_agent()

# approve_agent returns (response, agent_key) in current SDK versions. Be
# defensive about ordering: the agent key is the hex string that is NOT a dict.
agent_key = None
response = None
if isinstance(ret, tuple):
    for item in ret:
        if isinstance(item, str) and item.startswith("0x") and len(item) >= 60:
            agent_key = item
        else:
            response = item
else:
    response = ret

print("approve_agent raw return:")
print(" ", ret)
print()

if not agent_key:
    print("Could not auto-extract the agent key from the return above.")
    print("Look in the raw return for the 0x... private key string and use it as")
    print("HYPERLIQUID_AGENT_KEY. The response object is the on-chain confirmation.")
    sys.exit(1)

print("=== SET THESE FLY SECRETS (testnet first) ===")
print(f"HYPERLIQUID_AGENT_KEY={agent_key}")
print(f"HYPERLIQUID_MASTER_ADDRESS={master.address}")
print()
print("The agent key is TRADE-ONLY (cannot withdraw). Clear your shell history after copying.")
