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


# Roughly 500 words. Enough for real policy, small enough that it cannot quietly
# become the dominant cost of every question the workspace asks.
ASSISTANT_INSTRUCTIONS_MAX = 4000


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
    # D-128: where escalations go. Per workspace, and read only from here - never
    # from a request parameter - so one tenant's transcript can never be routed
    # to another tenant's helpdesk.
    support_email = models.EmailField(
        blank=True, help_text="Escalations are emailed here. Falls back to the platform default."
    )

    # Free-text workspace instructions, written by the tenant's own administrator
    # and injected into every prompt below the core rules (D-151).
    #
    # This is the policy a runbook cannot express: "we use Entra ID, not on-prem
    # AD", "never tell a user to reset their own password, send them to the
    # portal", "outside 9-6 GMT say the L2 team replies next working day".
    #
    # Trust level matters here. Retrieved runbook text is untrusted data (D-130)
    # because anyone who can upload a file can write it. This is deliberate
    # configuration by an authenticated administrator of that workspace - so it
    # is trusted, but BOUNDED: the prompt ranks it below the core rules and
    # states that it cannot switch off grounding, honesty about not knowing, or
    # escalation. A tenant may shape how the assistant speaks; not whether it
    # tells the truth.
    #
    # The cap is small on purpose. This text rides in EVERY request, so it is a
    # permanent per-question token cost, not a one-off.
    assistant_instructions = models.TextField(
        blank=True,
        max_length=ASSISTANT_INSTRUCTIONS_MAX,
        help_text=(
            "Workspace-specific guidance for the assistant: tools you use, local "
            "policy, house style. Cannot override grounding or escalation."
        ),
    )

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
