"""Identity.

Deliberately pulled forward from Phase 2. Django bakes AUTH_USER_MODEL into the
very first migration, and swapping it afterwards means destroying the database -
so the custom model has to exist before `migrate` runs even once (D-033).

Only the identity itself lives here. Tenant membership and roles
(PLATFORM_OWNER / TENANT_ADMIN / AGENT / END_USER) arrive in Phase 2 as
apps.tenancy.Membership, because a user is global and a role is per-tenant
(D-024, D-034).
"""

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    """Manager for an email-identified user - there is no username field."""

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        # set_password(None) produces an unusable password, which is what we
        # want for SSO-provisioned accounts that must never password-login.
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra.get("is_staff") is not True:
            raise ValueError("A superuser must have is_staff=True.")
        if extra.get("is_superuser") is not True:
            raise ValueError("A superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """A person. Global, not tenant-scoped.

    One human with one email is one User even when they belong to several
    workspaces; the workspaces are separate Membership rows (D-034). Email is
    normalised to lowercase on write so `Rizwan@x.com` and `rizwan@x.com`
    cannot become two accounts.
    """

    email = models.EmailField(unique=True, db_index=True)
    full_name = models.CharField(max_length=200, blank=True)
    job_title = models.CharField(max_length=120, blank=True)

    is_active = models.BooleanField(
        default=True,
        help_text="Unset to block sign-in without deleting history.",
    )
    is_staff = models.BooleanField(
        default=False,
        help_text="Django admin access. Unrelated to the tenant role model.",
    )

    date_joined = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        ordering = ("email",)
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self) -> str:
        return self.email

    def save(self, *args, **kwargs):
        self.email = self.email.lower().strip()
        return super().save(*args, **kwargs)

    @property
    def display_name(self) -> str:
        return self.full_name or self.email

    @property
    def initials(self) -> str:
        """Two-letter avatar initials, matching the prototype's avatar chips."""
        parts = [p for p in self.full_name.split() if p]
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        if parts:
            return parts[0][:2].upper()
        return self.email[:2].upper()


class PasswordResetCode(models.Model):
    """A one-time code that lets somebody back into their account (D-176).

    Codes rather than links, and the difference matters here. A link in an email
    is followed by scanners, previewed by clients and logged by proxies; a code
    has to be read by a person and typed back. It also keeps the flow on the
    origin the user started from, which a link cannot promise.

    Everything about this model exists because the code is a temporary password:

    * `code_hash`, never the code. A plaintext code in a database dump is an
      account, and this table is the one an attacker would go looking for.
    * `attempts`, because six digits is a million guesses and a patient script
      would find one. Five wrong tries kills the code rather than the request.
    * `expires_at`, because a code that lives in an inbox forever is a
      credential sitting in an inbox forever.
    * `used_at`, so a code that already worked cannot work twice - the second
      use would be somebody who read the first person's email.
    """

    ATTEMPT_LIMIT = 5
    LIFETIME_MINUTES = 15

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reset_codes"
    )
    code_hash = models.CharField(max_length=255, editable=False)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    # Kept for rate limiting and for the audit trail. A reset is the single most
    # useful event to have an address against when something goes wrong later.
    requested_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self) -> str:
        return f"reset for {self.user_id} at {self.created_at:%Y-%m-%d %H:%M}"

    @property
    def is_live(self) -> bool:
        """Usable right now. Three separate ways to be dead, and a caller that
        checked only expiry would honour a code that had already been used."""
        return (
            self.used_at is None
            and self.attempts < self.ATTEMPT_LIMIT
            and self.expires_at > timezone.now()
        )
