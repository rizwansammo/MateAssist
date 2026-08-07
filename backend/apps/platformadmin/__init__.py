"""Super-admin-only API surface, kept separate from tenant-facing routes.

Phase 4 delivered the credential vault endpoints (create / rotate / revoke /
purge / pool status) and ModelPrice management, all behind IsPlatformOwner.

These routes are reachable only on the platform host, which carries no tenant
subdomain - the permission class refuses any request that resolved a tenant.
"""
