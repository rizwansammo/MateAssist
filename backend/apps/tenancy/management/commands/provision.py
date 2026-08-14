"""Provision a production deployment (D-146).

    python manage.py provision

Creates exactly what a live install needs and nothing else: the platform owner,
one workspace, its administrator, one end user, and the model price rows.

**This is not seed_dev.** `seed_dev` creates Netswitch and Apptriangle with a
shared, published password, and its siblings `ingest_demo` and `seed_runbooks`
write demo documents into the corpus. None of them may ever run against a real
deployment - a customer discovering a "VPN Runbook (demo)" in their knowledge
base is the kind of thing that ends a pilot.

Every value is read from the environment. Hardcoding them would put a platform
owner's password in git, and the platform owner can read every workspace on the
installation.

Idempotent: safe to run on every deploy. An existing account keeps its password,
so re-running after someone has changed theirs does not silently reset it - pass
--reset-passwords when that is actually what you want.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connections, transaction
from django.utils import timezone

from apps.ai.models import ModelPrice
from apps.tenancy.models import Membership, Plan, Role, Tenant

# Published list rates in USD per million tokens (D-111).
#
# Seeded because `cost_usd` is computed and STORED when a usage row is written:
# an unpriced model records $0.00 permanently, and entering the rate later does
# not reprice traffic already recorded. A deployment that skips this accumulates
# a silent gap in its billing history.
PRICES = [
    # engine,  model,                 input/1M, output/1M, per image
    ("TEXT", "gemini-flash-latest", "0.30", "2.50", "0"),
    ("TEXT", "deepseek-chat", "0.27", "1.10", "0"),
    ("TEXT", "deepseek-reasoner", "0.55", "2.19", "0"),
    ("TEXT", "gpt-4o-mini", "0.15", "0.60", "0"),
    ("VISION", "gemini-3.6-flash", "0.30", "2.50", "0"),
]

REQUIRED = (
    "PLATFORM_OWNER_EMAIL",
    "PLATFORM_OWNER_PASSWORD",
    "TENANT_NAME",
    "TENANT_SLUG",
    "TENANT_ADMIN_EMAIL",
    "TENANT_ADMIN_PASSWORD",
)


class Command(BaseCommand):
    help = "Provision the platform owner, one workspace and its users from the environment."

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default="admin",
            help="Alias to write through. The owner connection is required because "
            "provisioning writes across tenants, which RLS refuses to the app role.",
        )
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="Overwrite existing accounts' passwords with the environment values. "
            "Off by default so a routine deploy cannot undo a password change.",
        )

    def handle(self, *args, **options):
        missing = [name for name in REQUIRED if not os.environ.get(name, "").strip()]
        if missing:
            self.stderr.write(
                "Refusing to provision - these environment variables are unset:\n  "
                + "\n  ".join(missing)
                + "\n\nSet them in the deployment .env. They are deliberately not "
                "defaulted: a fallback password would be a published credential."
            )
            sys.exit(1)

        alias = options["database"]
        reset = options["reset_passwords"]
        User = get_user_model()
        connection = connections[alias]

        owner_email = os.environ["PLATFORM_OWNER_EMAIL"].strip().lower()
        tenant_slug = os.environ["TENANT_SLUG"].strip().lower()

        with transaction.atomic(using=alias):
            # ---- platform owner -------------------------------------------
            # Written with no tenant armed: a PLATFORM_OWNER membership carries a
            # null tenant, and the RLS WITH CHECK clause refuses that row while a
            # tenant context is active.
            self._arm(connection, None)

            owner, owner_created = User.objects.using(alias).get_or_create(
                email=owner_email,
                defaults={
                    "full_name": os.environ.get("PLATFORM_OWNER_NAME", "Platform Owner"),
                    "is_staff": True,
                    "is_superuser": True,
                },
            )
            if owner_created or reset:
                owner.set_password(os.environ["PLATFORM_OWNER_PASSWORD"])
                owner.save(using=alias)

            Membership.all_objects.using(alias).get_or_create(
                user=owner, tenant=None, defaults={"role": Role.PLATFORM_OWNER}
            )

            # ---- the workspace --------------------------------------------
            tenant, tenant_created = Tenant.objects.using(alias).get_or_create(
                slug=tenant_slug,
                defaults={
                    "name": os.environ["TENANT_NAME"],
                    "plan": os.environ.get("TENANT_PLAN", Plan.ENTERPRISE),
                    "region": os.environ.get("TENANT_REGION", "us-east-1"),
                    # D-128: escalations are emailed here, read from the tenant
                    # row and never from a request parameter.
                    "support_email": os.environ.get("TENANT_SUPPORT_EMAIL", ""),
                },
            )

            self._arm(connection, tenant.id)

            members = [
                (
                    os.environ["TENANT_ADMIN_EMAIL"].strip().lower(),
                    os.environ["TENANT_ADMIN_PASSWORD"],
                    os.environ.get("TENANT_ADMIN_NAME", "Workspace Administrator"),
                    Role.TENANT_ADMIN,
                )
            ]
            if os.environ.get("TENANT_USER_EMAIL", "").strip():
                members.append(
                    (
                        os.environ["TENANT_USER_EMAIL"].strip().lower(),
                        os.environ.get("TENANT_USER_PASSWORD", os.environ["TENANT_ADMIN_PASSWORD"]),
                        os.environ.get("TENANT_USER_NAME", ""),
                        Role.END_USER,
                    )
                )

            created_users = []
            for email, password, full_name, role in members:
                user, created = User.objects.using(alias).get_or_create(
                    email=email, defaults={"full_name": full_name}
                )
                if created or reset:
                    user.set_password(password)
                    user.save(using=alias)
                if created:
                    created_users.append(email)
                Membership.all_objects.using(alias).get_or_create(
                    user=user, tenant=tenant, defaults={"role": role}
                )

            # ---- model prices ---------------------------------------------
            priced = 0
            for engine, model, input_rate, output_rate, per_image in PRICES:
                _row, made = ModelPrice.objects.using(alias).get_or_create(
                    engine=engine,
                    model=model,
                    effective_from=timezone.now().date(),
                    defaults={
                        "input_per_1m": Decimal(input_rate),
                        "output_per_1m": Decimal(output_rate),
                        "per_image": Decimal(per_image),
                    },
                )
                priced += 1 if made else 0

        # ---- report --------------------------------------------------------
        self.stdout.write(self.style.SUCCESS("\n  Provisioned.\n"))
        self.stdout.write(
            f"  Platform owner   {owner_email}  ({'created' if owner_created else 'existing'})"
        )
        self.stdout.write(
            f"  Workspace        {tenant.name} -> {tenant.slug}.{os.environ.get('BASE_DOMAIN', '')}"
            f"  ({'created' if tenant_created else 'existing'})"
        )
        for email, _password, _name, role in members:
            state = "created" if email in created_users else "existing"
            self.stdout.write(f"  {role:<16} {email}  ({state})")
        self.stdout.write(
            f"  Model prices     {priced} added, {len(PRICES) - priced} already present"
        )

        if not reset and not owner_created:
            self.stdout.write(
                self.style.WARNING(
                    "\n  Existing accounts kept their current passwords. "
                    "Use --reset-passwords to overwrite them."
                )
            )

        self.stdout.write(
            "\n  Next: sign in to the platform admin panel and add a provider key.\n"
            "  There is no key in the vault and no runbooks indexed, so the assistant\n"
            "  will correctly answer that it cannot help until both exist.\n"
        )

    @staticmethod
    def _arm(connection, tenant_id):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)",
                ["" if tenant_id is None else str(tenant_id)],
            )
