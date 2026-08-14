"""Create a usable development workspace.

    python manage.py seed_dev --database=admin

Runs against the admin (owner) alias because it writes across tenants, which is
exactly what RLS stops the runtime role doing.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connections, transaction
from django.utils import timezone

from apps.ai.models import ModelPrice
from apps.tenancy.models import Membership, Role, Tenant

PASSWORD = "MateAssist!2026"

TENANTS = [
    ("Netswitch", "netswitch", "ENTERPRISE"),
    ("Apptriangle", "apptriangle", "PRO"),
]

# Published list rates, in USD per million tokens (D-111).
#
# Seeded because `cost_usd` is computed and STORED when the usage row is written
# (see router._meter). An unpriced model records $0 forever - entering the rate
# tomorrow does not reprice yesterday's traffic, and it should not: a rate change
# must never silently rewrite an invoice that has already been issued. The
# consequence is that a deployment which never enters prices accumulates a
# permanent gap in its billing history, so a fresh install starts with figures
# rather than zeros.
#
# These are defaults, not gospel. Rates move; the platform admin edits them at
# /platform/prices, and `Summary.unpriced_models` names anything still missing.
PRICES = [
    # engine, model, input/1M, output/1M, per image
    ("TEXT", "gemini-flash-latest", "0.30", "2.50", "0"),
    ("TEXT", "deepseek-chat", "0.27", "1.10", "0"),
    ("TEXT", "deepseek-reasoner", "0.55", "2.19", "0"),
    ("VISION", "gemini-3.6-flash", "0.30", "2.50", "0"),
]


class Command(BaseCommand):
    help = "Seed development tenants, users and memberships."

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default="admin",
            help="Alias to write through. Defaults to the owner connection, which "
            "is required because seeding writes across tenants.",
        )

    def handle(self, *args, **options):
        alias = options.get("database") or "admin"
        User = get_user_model()
        connection = connections[alias]

        with transaction.atomic(using=alias):
            owner, _ = User.objects.using(alias).get_or_create(
                email="owner@mateassist.io",
                defaults={"full_name": "A. Siddiqui", "is_staff": True, "is_superuser": True},
            )
            owner.set_password(PASSWORD)
            owner.save(using=alias)

            with connection.cursor() as cursor:
                cursor.execute("SELECT set_config('app.tenant_id', '', true)")
            Membership.all_objects.using(alias).get_or_create(
                user=owner, tenant=None, defaults={"role": Role.PLATFORM_OWNER}
            )

            for name, slug, plan in TENANTS:
                tenant, _ = Tenant.objects.using(alias).get_or_create(
                    slug=slug, defaults={"name": name, "plan": plan}
                )
                with connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant.id)])

                for local, full_name, role in [
                    ("admin", f"{name} Admin", Role.TENANT_ADMIN),
                    ("rizwan", "Rizwan Ahmed", Role.END_USER),
                ]:
                    user, _ = User.objects.using(alias).get_or_create(
                        email=f"{local}@{slug}.test", defaults={"full_name": full_name}
                    )
                    user.set_password(PASSWORD)
                    user.save(using=alias)
                    Membership.all_objects.using(alias).get_or_create(
                        user=user, tenant=tenant, defaults={"role": role}
                    )

            for engine, model, input_rate, output_rate, per_image in PRICES:
                ModelPrice.objects.using(alias).get_or_create(
                    engine=engine,
                    model=model,
                    effective_from=timezone.now().date(),
                    defaults={
                        "input_per_1m": Decimal(input_rate),
                        "output_per_1m": Decimal(output_rate),
                        "per_image": Decimal(per_image),
                    },
                )

        self.stdout.write(self.style.SUCCESS("\n  Seeded development data.\n"))
        self.stdout.write(f"  Password for every account: {PASSWORD}\n")
        self.stdout.write("  Platform owner   owner@mateassist.io      (admin host)")
        for name, slug, _ in TENANTS:
            self.stdout.write(f"  {name:<16} admin@{slug}.test / rizwan@{slug}.test")
        self.stdout.write("")
