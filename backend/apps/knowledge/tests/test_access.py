"""Who can reach the runbooks directly (D-140).

Before this, `IsTenantAdmin` exempted GET. The browsable list was the visible
half of that; the half that mattered was `/knowledge/documents/{id}/chunks/`,
which returned the full text of any runbook to any authenticated member of the
workspace. Hiding the menu item would have changed nothing.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.knowledge.models import Document, DocumentChunk, DocumentStatus, FileType
from apps.tenancy.models import Membership, Role, Tenant
from apps.tenancy.tests.test_isolation import set_db_tenant

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def workspace():
    tenant = Tenant.objects.create(name="Netswitch", slug="netswitch")
    admin = User.objects.create_user("admin@netswitch.test", "correct-horse-battery")
    member = User.objects.create_user("rizwan@netswitch.test", "correct-horse-battery")

    set_db_tenant(tenant.id)
    Membership.all_objects.create(user=admin, tenant=tenant, role=Role.TENANT_ADMIN)
    Membership.all_objects.create(user=member, tenant=tenant, role=Role.END_USER)

    document = Document.all_objects.create(
        tenant=tenant,
        title="Accounts and MFA Runbook",
        storage_key="k",
        file_type=FileType.MD,
        size_bytes=10,
        checksum="c",
        status=DocumentStatus.INDEXED,
    )
    DocumentChunk.all_objects.create(
        tenant=tenant,
        document=document,
        ordinal=0,
        text="Verify identity by calling the number on record, never the number given.",
    )
    set_db_tenant(None)
    return tenant, admin, member, document


def client_for(user, tenant):
    client = APIClient()
    client.force_authenticate(user=user)
    client.defaults["HTTP_HOST"] = f"{tenant.slug}.localhost"
    return client


# ------------------------------------------------------------ end users -----


def test_an_end_user_cannot_list_runbooks(workspace):
    tenant, _admin, member, _document = workspace
    assert client_for(member, tenant).get("/api/v1/knowledge/documents/").status_code == 403


def test_an_end_user_cannot_read_a_runbooks_text(workspace):
    """The real exposure. A menu item can be hidden; this endpoint could not."""
    tenant, _admin, member, document = workspace

    response = client_for(member, tenant).get(f"/api/v1/knowledge/documents/{document.pk}/chunks/")

    assert response.status_code == 403
    assert b"calling the number on record" not in response.content


def test_an_end_user_cannot_read_figure_descriptions(workspace):
    tenant, _admin, member, document = workspace
    response = client_for(member, tenant).get(f"/api/v1/knowledge/documents/{document.pk}/assets/")
    assert response.status_code == 403


def test_an_end_user_cannot_list_categories(workspace):
    tenant, _admin, member, _document = workspace
    assert client_for(member, tenant).get("/api/v1/knowledge/categories/").status_code == 403


def test_an_end_user_still_cannot_upload(workspace):
    tenant, _admin, member, _document = workspace
    assert client_for(member, tenant).post("/api/v1/knowledge/documents/", {}).status_code == 403


# --------------------------------------------------------- administrators ---


def test_a_workspace_admin_still_has_full_access(workspace):
    tenant, admin, _member, document = workspace
    client = client_for(admin, tenant)

    assert client.get("/api/v1/knowledge/documents/").status_code == 200
    assert client.get(f"/api/v1/knowledge/documents/{document.pk}/chunks/").status_code == 200
    assert client.get("/api/v1/knowledge/categories/").status_code == 200


def test_an_anonymous_caller_gets_nothing(workspace):
    tenant, _admin, _member, _document = workspace
    client = APIClient()
    client.defaults["HTTP_HOST"] = f"{tenant.slug}.localhost"
    assert client.get("/api/v1/knowledge/documents/").status_code in (401, 403)


# ------------------------------------------------- the assistant is unaffected


def test_the_runbook_text_is_still_there_for_the_assistant(workspace):
    """The point is to remove *browsing*, not grounding.

    Retrieval reaches chunks through raw SQL scoped by RLS - it never passes
    through a DRF permission class - so tightening `IsTenantAdmin` cannot affect
    it by construction. This asserts the data is still reachable in the tenant's
    own context, which is the part worth pinning.

    The end-to-end claim, that an end user still gets grounded answers from
    runbooks they cannot browse, is proven by `manage.py gating_demo` against the
    real corpus. Repeating it here would mean loading the embedding model and
    reaching the network inside a unit test, for a weaker version of the same
    evidence.
    """
    tenant, _admin, _member, document = workspace
    set_db_tenant(tenant.id)

    chunks = DocumentChunk.all_objects.filter(document=document)

    assert chunks.exists(), "the corpus the assistant reads must be untouched"
    assert "number on record" in chunks.first().text
