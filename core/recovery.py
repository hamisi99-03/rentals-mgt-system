"""Local owner recovery code (shown once at setup)."""

import secrets

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError


def recovery_file():
    return settings.DATA_DIR / "instance" / "recovery_code.hash"


def generate_recovery_code():
    return "-".join(secrets.token_hex(3).upper() for _ in range(3))


def store_recovery_code(code):
    path = recovery_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(make_password(code), encoding="utf-8")


def has_recovery_code():
    return recovery_file().exists()


def verify_recovery_code(code):
    path = recovery_file()
    if not path.exists():
        return False
    return check_password(code.strip(), path.read_text(encoding="utf-8").strip())


def reset_owner_password(code, new_password, username=None):
    from django.contrib.auth.password_validation import validate_password
    from django.contrib.auth import get_user_model

    if not verify_recovery_code(code):
        raise ValidationError("The recovery code is not correct.")
    User = get_user_model()
    user = (
        User.objects.filter(username=username).first()
        if username
        else User.objects.order_by("id").first()
    )
    if user is None:
        raise ValidationError("There is no owner account to reset.")
    validate_password(new_password, user=user)
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
    return user
