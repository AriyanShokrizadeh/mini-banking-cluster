"""Install only new lab-administration scripts on VM1; never touch the running API."""

from __future__ import annotations

import subprocess
from uuid import uuid4

from scripts.demos.recording_support import ROOT, DemoFailure

TOOLS = ("prepare_lab.py", "cleanup_legacy_demo.py")
TARGET = "/opt/mini-banking-releases/scripts/setup"


def install(host: str) -> None:
    stage = f"mini-banking-demo-stage-{uuid4().hex[:12]}"
    remote_stage = f"$HOME/{stage}"
    try:
        _run(["ssh", "-tt", host, f"mkdir -m 700 {remote_stage}"])
        _run(
            [
                "scp",
                "-q",
                *(str(ROOT / "scripts" / "setup" / name) for name in TOOLS),
                f"{host}:{stage}/",
            ]
        )
        commands = [
            "sudo test -x /opt/mini-banking-releases/.venv/bin/python",
            "sudo test -f /etc/mini-banking/banking.env",
            *(
                f"sudo install -o banking -g banking -m 644 {remote_stage}/{name} {TARGET}/{name}"
                for name in TOOLS
            ),
        ]
        _run(["ssh", "-tt", host, " && ".join(commands)])
        print("PASS | VM1 demo setup tools deployed; banking-api was not restarted")
    finally:
        cleanup = " && ".join(
            [*(f"rm -f {remote_stage}/{name}" for name in TOOLS), f"rmdir {remote_stage}"]
        )
        subprocess.run(["ssh", "-tt", host, cleanup], check=False)


def _run(command: list[str]) -> None:
    result = subprocess.run(command, check=False)
    if result.returncode:
        raise DemoFailure(f"Deployment step failed (exit {result.returncode}): {command[0]}")
