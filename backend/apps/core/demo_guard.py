"""Refuse to run demo tooling against a real deployment (D-146).

Several management commands exist to make a phase gate provable, and all of them
write data a customer must never see:

    seed_dev        Netswitch and Apptriangle, with a password in the repository
    ingest_demo     "VPN Runbook (demo)" into the knowledge base
    seed_runbooks   four fabricated runbooks, including a second VPN client
    chat_demo       conversations and metered usage against real quota
    usage_demo      synthetic usage events and a temporary budget

Each is correct in development and indefensible in production. A customer who
finds "VPN Runbook (demo)" in their own knowledge base has been shown that their
install is somebody's test environment, and no amount of explanation undoes it.

The guard is deliberately not "am I in DEBUG mode". A misconfigured deployment
with DEBUG accidentally left on would sail through that check - which is exactly
the deployment most likely to have other things wrong with it too. Instead the
command must be *explicitly* permitted, so running it anywhere requires someone
to have said so on purpose.
"""

from __future__ import annotations

import os
import sys

ENV_FLAG = "MATEASSIST_ALLOW_DEMO_DATA"


def refuse_in_production(command, *, what: str) -> None:
    """Exit unless demo data is explicitly permitted in this environment.

    `what` names the data that would be written, so the refusal explains itself
    rather than just denying.
    """
    if os.environ.get(ENV_FLAG, "").strip().lower() in ("1", "true", "yes"):
        return

    command.stderr.write(
        f"\nRefusing to run: this command writes {what}.\n\n"
        f"Set {ENV_FLAG}=1 to allow it. That variable is absent from the\n"
        "production .env on purpose, so a deploy script or a mistyped command\n"
        "cannot put demo data into a customer's workspace.\n\n"
        "For a real deployment you want `manage.py provision` instead, which\n"
        "creates the platform owner, one workspace and its users from the\n"
        "environment - and nothing else.\n"
    )
    sys.exit(1)
