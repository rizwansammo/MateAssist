from rest_framework.permissions import BasePermission

from apps.tenancy.models import Membership, Role


class IsPlatformOwner(BasePermission):
    """Platform-owner only.

    Checked against the database rather than a token claim: claims are a client
    convenience and revoking a role must take effect immediately, not at the
    next token issue.

    A platform owner has a membership with a null tenant, so this also refuses
    anyone signed in on a tenant subdomain - the admin surface lives on its own
    host (D-145).
    """

    message = "Platform owner access required."

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(request, "tenant", None) is not None:
            return False
        return Membership.all_objects.filter(
            user=request.user, tenant__isnull=True, role=Role.PLATFORM_OWNER
        ).exists()
