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

# Per rule. Short enough that a rule stays a rule rather than becoming an essay
# with a checkbox next to it.
ASSISTANT_RULE_MAX = 500


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

    # The person who owns this workspace commercially (D-173).
    #
    # Deliberately NOT a fifth Role. A role drives the permission matrix, and
    # adding one means touching every check and every test; ownership is an
    # identity and billing fact, not a permission. The owner holds TENANT_ADMIN
    # like any other administrator - this field only says which of them is THE
    # one, which a role cannot express because a role cannot be limited to one
    # holder.
    #
    # SET_NULL, not CASCADE: deleting a person must never delete the company.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_workspaces",
        help_text="The workspace's primary administrator.",
    )
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

    # ---- outbound mail, per workspace (D-154) -----------------------------
    #
    # Escalations are sent FROM the workspace, not from the platform. That is a
    # deliverability requirement, not a preference: an email whose From address
    # says @customer.com but which leaves a server the customer's SPF record
    # does not authorise gets filed as spam, and the one message that matters -
    # a user's unresolved problem reaching a human - is the one that vanishes.
    #
    # All blank means "use the platform's own mail settings", so a workspace
    # that does not care still works.
    smtp_host = models.CharField(max_length=255, blank=True)
    smtp_port = models.PositiveIntegerField(default=587)
    smtp_username = models.CharField(max_length=255, blank=True)

    # Sealed with the same AES-256-GCM vault as provider credentials (D-071).
    # There is no field, serializer or endpoint that returns it - the API can
    # only report whether one is set. Storing an SMTP password in a plain column
    # would put a working mail credential in every database dump.
    smtp_password_ciphertext = models.TextField(blank=True, editable=False)

    # The name a recipient sees instead of a raw address (D-162).
    #
    # Escalations landed in Gmail's spam folder showing only
    # "aiassist.netamate" - a bare local part with no human name attached. SPF
    # and DKIM were passing, so authentication was never the problem: an
    # unnamed sender mailing repetitive templated text to an address that has
    # never replied simply looks like bulk mail.
    #
    # Blank falls back to the workspace's own name, which is nearly always what
    # an administrator would have typed anyway.
    smtp_from_name = models.CharField(
        max_length=120,
        blank=True,
        help_text="Display name on escalation emails. Defaults to the workspace name.",
    )
    smtp_use_tls = models.BooleanField(default=True)
    smtp_from_email = models.EmailField(
        blank=True,
        help_text=(
            "The From address on escalation emails. Must be one your mail server "
            "is allowed to send as."
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

    # ---- SMTP credential handling ----------------------------------------

    @property
    def workspace_instructions(self) -> str:
        """The enabled rules, joined for the prompt (D-167).

        The model still receives one block - splitting the UI into rows changed
        how they are WRITTEN, not how they are read. Disabled rules are excluded
        here rather than filtered at the call site, so a caller cannot forget
        and quietly reinstate a rule someone deliberately turned off.
        """
        rules = self.assistant_rules.filter(enabled=True).order_by("position", "id")
        return "\n\n".join(rule.text for rule in rules)

    @property
    def smtp_vault_context(self) -> str:
        """Binds the ciphertext to this row, so a blob lifted from one tenant
        cannot be decrypted as another's (D-071)."""
        return f"tenant-smtp:{self.pk}"

    @property
    def has_smtp(self) -> bool:
        """Enough configuration to send. A host alone is not enough - a server
        that needs auth and gets none fails at send time, which is the worst
        moment to discover it."""
        return bool(self.smtp_host and self.smtp_from_email)

    def set_smtp_password(self, secret: str) -> None:
        from apps.ai import vault

        secret = (secret or "").strip()
        self.smtp_password_ciphertext = (
            vault.seal(secret, context=self.smtp_vault_context) if secret else ""
        )

    def reveal_smtp_password(self) -> str:
        """Decrypt for an outbound connection. Never for display - nothing in
        the API returns this, by construction rather than by flag."""
        from apps.ai import vault

        if not self.smtp_password_ciphertext:
            return ""
        return vault.open_sealed(self.smtp_password_ciphertext, context=self.smtp_vault_context)


class AssistantRule(models.Model):
    """One workspace instruction, as its own row (D-167).

    These were a single 4000-character textarea. Same data, but a blank box that
    size is intimidating: people opened it, could not tell what belonged in it,
    and closed it again. "Add a rule" asks for one sentence, which is a far
    smaller thing to agree to - and someone who writes one usually writes three.

    Separate rows also buy things a textarea cannot:

    - correcting one line cannot accidentally break another
    - `enabled` turns a rule off for a holiday shutdown without losing the
      wording, which is what deleting it would cost
    - `position` makes the read order visible, since the model reads them top
      to bottom and an essay hides that entirely

    The model still receives one joined block, so nothing about prompting
    changes. This is about whether a human will write them at all.
    """

    tenant = models.ForeignKey(
        "tenancy.Tenant", on_delete=models.CASCADE, related_name="assistant_rules"
    )
    text = models.TextField(max_length=ASSISTANT_RULE_MAX)
    enabled = models.BooleanField(
        default=True, help_text="Turn off temporarily without losing the wording."
    )
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("position", "id")
        indexes = [models.Index(fields=["tenant", "position"])]

    def __str__(self) -> str:
        return self.text[:60]


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
