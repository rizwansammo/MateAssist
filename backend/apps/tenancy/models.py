"""Tenancy: the Tenant registry and per-tenant Membership.

Isolation is enforced by PostgreSQL RLS (D-020), not by these classes. The
managers here are convenience and defence in depth (D-022); the database is the
guarantee.
"""

from django.conf import settings
from django.db import models

from .managers import TenantScopedManager


class Role(models.TextChoices):
    PLATFORM_OWNER = "PLATFORM_OWNER", "Platform owner"
    TENANT_ADMIN = "TENANT_ADMIN", "Tenant admin"
    AGENT = "AGENT", "Agent"
    END_USER = "END_USER", "End user"


class Plan(models.TextChoices):
    GROWTH = "GROWTH", "Growth"
    PRO = "PRO", "Pro"
    ENTERPRISE = "ENTERPRISE", "Enterprise"


class Tenant(models.Model):
    """A customer workspace.

    Not itself RLS-protected: this is the registry, not tenant data. Tenant-owned
    tables carry a tenant_id and are policy-protected.
    """

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        SUSPENDED = "SUSPENDED", "Suspended"

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=63, unique=True, db_index=True)
    plan = models.CharField(max_length=20, choices=Plan.choices, default=Plan.GROWTH)
    region = models.CharField(max_length=32, default="eu-central-1")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.ACTIVE

    @property
    def subdomain(self) -> str:
        return f"{self.slug}.{settings.BASE_DOMAIN}"


class Membership(models.Model):
    """Links a user to a workspace with a role.

    A user is global; a role is per-tenant (D-034). PLATFORM_OWNER is the one
    role that is not tenant-scoped, so it carries a null tenant - enforced by a
    database constraint rather than trusted to application code.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="memberships", null=True, blank=True
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.END_USER)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantScopedManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ("tenant__name", "user__email")
        constraints = [
            models.UniqueConstraint(fields=["user", "tenant"], name="uniq_membership_user_tenant"),
            models.CheckConstraint(
                name="platform_owner_has_no_tenant",
                condition=(
                    models.Q(role="PLATFORM_OWNER", tenant__isnull=True)
                    | (~models.Q(role="PLATFORM_OWNER") & models.Q(tenant__isnull=False))
                ),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}@{self.tenant_id or 'platform'}:{self.role}"
