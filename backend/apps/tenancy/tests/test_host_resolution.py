"""Which host means which workspace (D-148).

The bug this exists to prevent shipped to production and was found by trying to
log in: `_subdomain` took the first label of the host and called it a slug, so
the apex `mateassist.site` resolved to a workspace named "mateassist", found
none, and returned 404 "Unknown workspace" for every request to the platform
surface - including the platform owner's login.

Development could not catch it. BASE_DOMAIN was `localhost:8000`, and localhost
is a single label, so the old length check returned None and the apex worked for
the wrong reason. The failure needed a real two-label domain to appear.

So these tests run against a realistic BASE_DOMAIN rather than the dev one.
"""

import pytest

from apps.tenancy.middleware import _subdomain


@pytest.fixture
def real_domain(settings):
    """A realistic two-label apex - the shape that exposed the bug."""
    settings.BASE_DOMAIN = "mateassist.site"


@pytest.fixture
def dev_domain(settings):
    settings.BASE_DOMAIN = "localhost:8000"


@pytest.mark.usefixtures("real_domain")
class TestRealDomain:
    def test_the_apex_is_the_platform_surface(self):
        """The regression. IsPlatformOwner requires request.tenant to be None,
        so if the apex resolves to a workspace the platform panel is
        unreachable - which is exactly what happened."""
        assert _subdomain("mateassist.site") is None

    def test_a_subdomain_is_a_workspace(self):
        assert _subdomain("netamate.mateassist.site") == "netamate"

    def test_the_port_is_ignored(self):
        assert _subdomain("netamate.mateassist.site:443") == "netamate"
        assert _subdomain("mateassist.site:8000") is None

    def test_case_is_ignored(self):
        assert _subdomain("NetaMate.MateAssist.Site") == "netamate"

    def test_a_trailing_dot_is_ignored(self):
        """`host.` is a legal fully-qualified name and some clients send it."""
        assert _subdomain("netamate.mateassist.site.") == "netamate"
        assert _subdomain("mateassist.site.") is None

    def test_www_is_not_a_workspace(self):
        """Otherwise www renders a login screen for a workspace that does not
        exist, while the API refuses every call it makes."""
        assert _subdomain("www.mateassist.site") is None

    def test_reserved_labels_are_not_workspaces(self):
        for label in ("admin", "api", "mail", "static"):
            assert _subdomain(f"{label}.mateassist.site") is None

    def test_deeper_nesting_is_not_a_workspace(self):
        """`a.b.mateassist.site` is not workspace "a.b" - a slug cannot contain
        a dot, and treating it as one would let a host invent slugs."""
        assert _subdomain("a.b.mateassist.site") is None

    def test_a_foreign_host_resolves_to_no_workspace(self):
        """An unrecognised host must not be read as a tenant. Falling through to
        the platform surface means it gets refused; falling through to a tenant
        would mean a stranger's data."""
        assert _subdomain("mateassist.site.evil.example") is None
        assert _subdomain("example.com") is None
        assert _subdomain("netamate.matedesk.pro") is None


@pytest.mark.usefixtures("dev_domain")
class TestDevelopmentDomain:
    """The dev setup must keep working, since it is what everyone runs locally."""

    def test_bare_localhost_is_the_platform_surface(self):
        assert _subdomain("localhost:8000") is None
        assert _subdomain("localhost") is None

    def test_a_dev_subdomain_is_a_workspace(self):
        assert _subdomain("netswitch.localhost:5175") == "netswitch"

    def test_127_0_0_1_is_not_a_workspace(self):
        """It does not end in .localhost, so it is not a tenant host - and
        reading "127" as a slug is how the old implementation behaved."""
        assert _subdomain("127.0.0.1:8000") is None


def test_an_unset_base_domain_never_resolves_a_workspace(settings):
    """Fail closed. A misconfigured deployment should serve nobody's data rather
    than guess which label might be a slug."""
    settings.BASE_DOMAIN = ""
    assert _subdomain("netamate.mateassist.site") is None
