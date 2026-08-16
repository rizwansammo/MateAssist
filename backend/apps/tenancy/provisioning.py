"""Creating a workspace, and creating people in one (D-173).

Until this existed, every account on the platform came from a management command
run over SSH. Onboarding a second customer, or a single new hire, needed someone
with server access - which is not a product.

Two levels, deliberately separate:

* the platform owner creates a WORKSPACE and its first administrator
* that administrator creates people inside their own workspace, and nowhere else

Both go through here rather than through their views, because each is several
writes that must not half-happen. A workspace with no administrator is
unreachable and invisible; a user row with no membership can sign in and belongs
nowhere.
"""

from __future__ import annotations

import secrets

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils.text import slugify

from .context import db_tenant_scope
from .models import Membership, Role, Tenant

# Reserved because they are already routes or hostnames. A workspace at
# `admin.mateassist.site` would shadow the console; one at `www` or `api` would
# be unreachable behind whatever answers there today.
RESERVED_SLUGS = {
    "admin",
    "api",
    "app",
    "assets",
    "auth",
    "billing",
    "cdn",
    "dashboard",
    "docs",
    "help",
    "mail",
    "platform",
    "platform_admin",
    "static",
    "status",
    "support",
    "www",
}


class ProvisioningError(Exception):
    """Something the caller can show a person, not a stack trace."""


def unique_slug(name: str, *, requested: str = "") -> str:
    """A DNS-safe, unused subdomain label.

    Derived rather than required, because `POST /platform/tenants/` accepted a
    name and left `slug` read-only - so the first workspace created through the
    API got an empty slug and was unreachable, and the second collided with it
    on the unique constraint and returned a 500.

    Collisions get a numeric suffix instead of an error: "Acme" and "Acme Ltd"
    are different customers who both want `acme`, and failing the second is a
    worse answer than `acme-2`.
    """
    base = slugify(requested or name)[:56].strip("-")
    if not base:
        raise ProvisioningError("That workspace name has no letters or numbers in it.")

    candidate = base if base not in RESERVED_SLUGS else f"{base}-workspace"
    suffix = 2
    while Tenant.objects.filter(slug=candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def generate_password() -> str:
    """A password that survives being read down a phone line.

    `secrets`, not `random`: this is a credential. The alphabet drops the
    characters people mishear or mistype - no O/0, no l/1/I.
    """
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    return "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(3))


def check_password_strength(password: str, user=None) -> None:
    try:
        validate_password(password, user)
    except DjangoValidationError as exc:
        raise ProvisioningError(" ".join(exc.messages)) from exc


def _claim_email(email: str) -> str:
    """Normalise, and refuse an address that already exists anywhere.

    `User` is global: one person with one address is one account across every
    workspace. Attaching an existing user to a second workspace is a real
    operation, but not this one - doing it silently here would add someone to a
    company they never agreed to join, on the say-so of that company's admin.
    """
    email = (email or "").strip().lower()
    if not email:
        raise ProvisioningError("An email address is required.")

    if get_user_model().objects.filter(email=email).exists():
        raise ProvisioningError("An account already exists for that address.")
    return email


@transaction.atomic
def create_workspace(
    *,
    name: str,
    admin_email: str,
    admin_name: str = "",
    admin_password: str = "",
    slug: str = "",
    plan: str = "",
    support_email: str = "",
) -> dict:
    """A workspace and its first administrator, or neither.

    Atomic on purpose. A workspace with no administrator cannot be signed into
    and does not appear in anyone's list, so a half-finished create leaves a row
    only the database knows about.
    """
    name = (name or "").strip()
    if not name:
        raise ProvisioningError("A workspace name is required.")

    email = _claim_email(admin_email)
    password = (admin_password or "").strip() or generate_password()
    check_password_strength(password)

    tenant = Tenant.objects.create(
        name=name,
        slug=unique_slug(name, requested=slug),
        plan=plan or Tenant._meta.get_field("plan").default,
        support_email=(support_email or "").strip(),
    )

    User = get_user_model()
    owner = User.objects.create_user(email, password, full_name=(admin_name or "").strip())

    # Armed for the new workspace before writing its membership. A platform
    # request has no tenant on the session, so the RLS WITH CHECK clause demands
    # `tenant_id IS NULL` and refuses this row outright - "new row violates row
    # level security policy". The policy is right; it just has to be told which
    # workspace the row belongs to.
    with db_tenant_scope(tenant.pk):
        Membership.all_objects.create(user=owner, tenant=tenant, role=Role.TENANT_ADMIN)

    tenant.owner = owner
    tenant.save(update_fields=["owner"])

    return {"tenant": tenant, "owner": owner, "password": password}


@transaction.atomic
def create_member(
    *, tenant, email: str, full_name: str = "", password: str = "", role: str = ""
) -> dict:
    """A person inside one workspace.

    `tenant` comes from the request, never from the payload. A tenant admin
    naming a different workspace is then not refused - it is unrepresentable.
    """
    address = _claim_email(email)
    secret = (password or "").strip() or generate_password()
    check_password_strength(secret)

    if role and role not in {Role.END_USER, Role.AGENT, Role.TENANT_ADMIN}:
        raise ProvisioningError("That is not a role you can assign.")

    User = get_user_model()
    user = User.objects.create_user(address, secret, full_name=(full_name or "").strip())

    # Armed explicitly rather than relying on the request's context. This is
    # called from a tenant request that already has it, but a management command
    # or a task would not - and the failure there is a refused INSERT at the
    # worst moment rather than at import time.
    with db_tenant_scope(tenant.pk):
        Membership.all_objects.create(user=user, tenant=tenant, role=role or Role.END_USER)

    return {"user": user, "password": secret}
