"""
Modal serverless deployment for the Blender proof-of-life agent.

Architecture:
- A single long-running Modal Function holds the Hermes Agent daemon.
- Modal Functions max out at 24h runtime; we schedule a daily restart so
  the daemon never hits the wall mid-action. Hermes Agent state lives on
  a Modal Volume so it survives the restart.
- A second scheduled Function ("ping") wakes once per hour to tail the
  agent log and exit. This is a cheap liveness probe.

Cost on Modal free tier ($30/month credit): a tiny long-running container
plus 24 hourly pings comes in well under $5/month. OpenRouter free-tier
Hermes 3 405B is $0 for inference. Total run cost ~$0-5/month.

Deploy:
    modal token set --token-id <id> --token-secret <secret>
    modal secret create hermes-secrets OPENROUTER_API_KEY=<key>
    modal deploy modal_deploy.py

Tear down:
    modal app stop blender-agent
    modal volume rm hermes-data
"""
import modal

APP_NAME = "blender-agent"
VOLUME_NAME = "hermes-data"
SECRET_NAME = "hermes-secrets"

app = modal.App(APP_NAME)

# Persistent state for the agent: ~/.hermes lives here so it survives restarts.
volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

# Container image: Python 3.11 + Hermes Agent + this project's templates.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "curl", "ca-certificates")
    .pip_install("hermes-agent")
    .add_local_dir(".", remote_path="/agent-template")
)


@app.function(
    image=image,
    volumes={"/root/.hermes": volume},
    secrets=[modal.Secret.from_name(SECRET_NAME)],
    timeout=86400,  # 24 hours max per Modal limits; daemon respawns daily.
    schedule=modal.Cron("0 0 * * *"),  # restart daily at 00:00 UTC.
    cpu=0.25,
    memory=512,
)
def run_daemon():
    """Long-running Hermes Agent daemon. Restarted every 24h by Modal."""
    import os
    import shutil
    import subprocess
    from pathlib import Path

    hermes_dir = Path("/root/.hermes")
    hermes_dir.mkdir(parents=True, exist_ok=True)

    # First-boot setup: copy template files into the persistent volume if absent.
    if not (hermes_dir / "config.yaml").exists():
        shutil.copy("/agent-template/config.yaml", hermes_dir / "config.yaml")
        print("[deploy] copied config.yaml into volume")
    if not (hermes_dir / "SOUL.md").exists():
        shutil.copy("/agent-template/SOUL.md", hermes_dir / "SOUL.md")
        print("[deploy] copied SOUL.md into volume")

    # Bootstrap crons (idempotent).
    print("[deploy] registering crons")
    subprocess.run(
        ["python", "/agent-template/bootstrap_crons.py"],
        check=False,  # bootstrap script tolerates already-existing crons
    )

    # Persist any volume changes from the bootstrap.
    volume.commit()

    # Run the gateway daemon. Blocks until container shutdown.
    print("[deploy] starting hermes gateway")
    subprocess.run(["hermes", "gateway", "start"], check=True)


@app.function(
    image=image,
    volumes={"/root/.hermes": volume},
    schedule=modal.Cron("0 * * * *"),  # hourly liveness probe
    cpu=0.1,
    memory=128,
)
def ping():
    """Hourly liveness probe. Tails the cron output dir and prints summary."""
    from pathlib import Path

    cron_out = Path("/root/.hermes/cron/output")
    if not cron_out.exists():
        print("[ping] no cron output yet")
        return

    by_job = {}
    for job_dir in cron_out.iterdir():
        if not job_dir.is_dir():
            continue
        runs = sorted(job_dir.glob("*.md"))
        by_job[job_dir.name] = {
            "runs": len(runs),
            "latest": runs[-1].name if runs else None,
        }
    print(f"[ping] cron run summary: {by_job}")
