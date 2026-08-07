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
