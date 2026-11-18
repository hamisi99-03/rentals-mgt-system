"""One central place for access checks.

The app has a single owner account (see docs/SCHEMA.md). Access is therefore
authentication-only. Keeping this in one function means a second user with a
role could be added later without touching every view.
"""

from functools import wraps

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


def can_access(user, action="view", obj=None) -> bool:
    """Return True when the user may perform `action`. All actions are equal."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    return bool(getattr(user, "is_active", False))


def role_required(view_func):
    """Kept as the single view gate; roles were removed from the schema."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not can_access(request.user):
            raise PermissionDenied("This account cannot access the application.")
        return view_func(request, *args, **kwargs)

    return _wrapped


class RoleRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not can_access(request.user):
            raise PermissionDenied("This account cannot access the application.")
        return super(LoginRequiredMixin, self).dispatch(request, *args, **kwargs)
