"""Current-tenant context.

A ContextVar rather than thread-local: the app runs under ASGI (D-003), where a
single thread interleaves many requests and a thread-local would leak one
tenant's identity into another's request.
"""

from contextlib import contextmanager
from contextvars import ContextVar

_current_tenant_id: ContextVar[int | None] = ContextVar("current_tenant_id", default=None)


def get_current_tenant_id() -> int | None:
    return _current_tenant_id.get()


def set_current_tenant_id(tenant_id: int | None):
    return _current_tenant_id.set(tenant_id)


def reset_current_tenant_id(token) -> None:
    _current_tenant_id.reset(token)


@contextmanager
def tenant_context(tenant_id: int | None):
    token = set_current_tenant_id(tenant_id)
    try:
        yield
    finally:
        reset_current_tenant_id(token)


@contextmanager
def platform_scope():
    """Read platform-scope rows (tenant IS NULL) during a tenant request.

    The RLS policy is `tenant_id = app_current_tenant_id()` while a tenant is
    armed, so rows with a NULL tenant - platform ownership, above all - are
    invisible from inside a workspace request. A query for them returns nothing
    and reports it as a clean, empty, entirely believable result.

    That is a dangerous shape for a SECURITY CHECK. "Is this person a platform
    owner?" answered `no` because the row was filtered, not because it was
    absent, and the guard it protected passed. This clears the setting for the
    duration of the block and restores it afterwards, so such a question is
    asked where it can actually be answered.

    Same connection and same transaction, deliberately: the `admin` alias would
    also see the row, but it is a separate session that cannot see anything the
    current transaction has not committed.
    """
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT app_current_tenant_id()")
        previous = cursor.fetchone()[0]
        cursor.execute("SELECT set_config('app.tenant_id', '', true)")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)",
                ["" if previous is None else str(previous)],
            )


@contextmanager
def db_tenant_scope(tenant_id: int):
    """Arm the database session for one workspace, then put it back.

    The inverse of `platform_scope`. A platform request has no tenant armed, so
    the RLS WITH CHECK clause demands `tenant_id IS NULL` and refuses any
    tenant-owned row - which is correct, and is exactly what a platform owner
    creating a workspace's first membership runs into.

    Arming the session is the honest fix. Writing through the RLS-bypassing
    owner connection would also work and would quietly move a write off the
    policy-enforced path; this keeps the policy in force and simply tells it
    which workspace the row belongs to.

    `set_config(..., true)` is transaction-scoped, so callers doing several
    writes should hold a transaction around this block.
    """
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT app_current_tenant_id()")
        previous = cursor.fetchone()[0]
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant_id)])
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.tenant_id', %s, true)",
                ["" if previous is None else str(previous)],
            )
