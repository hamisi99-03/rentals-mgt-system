"""Attach the current request user to a thread-local for automatic audit stamps."""

import threading
from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

_local = threading.local()


def get_current_user():
    user = getattr(_local, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return user
    return None


def set_current_user(user):
    _local.user = user


class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        set_current_user(getattr(request, "user", None))
        try:
            return self.get_response(request)
        finally:
            set_current_user(None)

class IdleLockMiddleware:
    """Lock the single owner session after the configured inactivity period."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            limit = getattr(user, "auto_lock_minutes", 15) or 15
            now = timezone.now()
            last_raw = request.session.get("last_activity")
            if last_raw:
                try:
                    last = datetime.fromisoformat(last_raw)
                except (TypeError, ValueError):
                    last = None
                if last is not None and now - last > timedelta(minutes=limit):
                    logout(request)
                    messages.info(
                        request,
                        "Screen locked after inactivity. Sign in again to continue.",
                    )
                    return redirect(reverse("login") + "?locked=1")
            request.session["last_activity"] = now.isoformat()
        return self.get_response(request)
