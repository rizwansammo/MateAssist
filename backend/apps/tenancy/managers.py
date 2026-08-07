"""Tenant-scoped ORM helpers.

Convenience and defence in depth (D-022). These filters are NOT the isolation
guarantee - RLS is. A query that bypasses this manager still cannot cross
tenants, which is the whole point of enforcing at the storage layer.
"""

from django.db import models

from .context import get_current_tenant_id


class TenantScopedQuerySet(models.QuerySet):
    def for_current_tenant(self):
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            # Fail closed. An unset tenant means "no tenant", never "all tenants".
            return self.none()
        return self.filter(tenant_id=tenant_id)


class TenantScopedManager(models.Manager.from_queryset(TenantScopedQuerySet)):
    def get_queryset(self):
        return super().get_queryset().for_current_tenant()


class TenantScopedModel(models.Model):
    """Base for tenant-owned models. Phases 3-7 inherit from this."""

    tenant = models.ForeignKey(
        "tenancy.Tenant", on_delete=models.CASCADE, related_name="%(class)ss"
    )

    objects = TenantScopedManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True
