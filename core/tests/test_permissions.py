import pytest
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory

from core.permissions import can_access, role_required


@pytest.mark.django_db
def test_active_owner_has_access(django_user_model):
    user = django_user_model.objects.create_user(username="owner", password="secret-pass-123")
    for action in ("view", "create", "update", "delete", "void"):
        assert can_access(user, action) is True


@pytest.mark.django_db
def test_inactive_user_is_denied(django_user_model):
    user = django_user_model.objects.create_user(
        username="inactive", password="secret-pass-123", is_active=False
    )
    assert can_access(user) is False


def test_anonymous_user_is_denied():
    assert can_access(None) is False


@pytest.mark.django_db
def test_role_required_redirects_anonymous(client):
    response = client.get("/units/")
    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


@pytest.mark.django_db
def test_role_required_rejects_inactive_user(django_user_model):
    user = django_user_model.objects.create_user(
        username="inactive", password="secret-pass-123", is_active=False
    )

    @role_required
    def protected(request):
        return None

    request = RequestFactory().get("/protected/")
    request.user = user
    with pytest.raises(PermissionDenied):
        protected(request)
