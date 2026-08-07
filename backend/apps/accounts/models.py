"""Identity.

Deliberately pulled forward from Phase 2. Django bakes AUTH_USER_MODEL into the
very first migration, and swapping it afterwards means destroying the database -
so the custom model has to exist before `migrate` runs even once (D-033).

Only the identity itself lives here. Tenant membership and roles
(PLATFORM_OWNER / TENANT_ADMIN / AGENT / END_USER) arrive in Phase 2 as
apps.tenancy.Membership, because a user is global and a role is per-tenant
(D-024, D-034).
"""

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
