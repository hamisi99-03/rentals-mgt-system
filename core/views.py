import json
import os
import platform
import zipfile
from io import BytesIO

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.views import LoginView, LogoutView
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.backup import backup_status, default_backup_folder, perform_backup
from core.forms import AppearanceForm, SettingsForm, StyledAuthenticationForm
from core.models import AuditLog, BackupLog, Settings, User
from core.permissions import role_required
from core.recovery import (
    generate_recovery_code,
    has_recovery_code,
    store_recovery_code,
)
from core.setup_forms import SetupForm
from property.services import refresh_lease_statuses
from reports.services import dashboard_summary


class AppLoginView(LoginView):
    authentication_form = StyledAuthenticationForm
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        if not User.objects.exists():
            return redirect("setup")
        return super().dispatch(request, *args, **kwargs)


class AppLogoutView(LogoutView):
    next_page = "login"


@role_required
def dashboard(request):
    refresh_lease_statuses()
    return render(
        request,
        "core/dashboard.html",
        {"summary": dashboard_summary(), "backup_status": backup_status()},
    )


@role_required
def settings_view(request):
    instance = Settings.load()
    if request.method == "POST":
        form = SettingsForm(
            request.POST, request.FILES, instance=instance, user=request.user
        )
        if form.is_valid():
            form.save()
            minutes = form.cleaned_data["auto_lock_minutes"]
            if request.user.auto_lock_minutes != minutes:
                request.user.auto_lock_minutes = minutes
                request.user.save(update_fields=["auto_lock_minutes"])
            messages.success(request, "Settings saved.")
            return redirect("settings")
        messages.error(request, "Please correct the errors below.")
    else:
        form = SettingsForm(instance=instance, user=request.user)
    return render(request, "core/settings.html", {"form": form})


@role_required
def appearance(request):
    if request.method == "POST":
        form = AppearanceForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Appearance saved.")
            return redirect("appearance")
        messages.error(request, "Please choose a valid appearance.")
    else:
        form = AppearanceForm(instance=request.user)
    return render(request, "core/appearance.html", {"form": form})


@require_POST
@role_required
def appearance_theme_save(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "error": "Invalid payload."}, status=400)

    data = {
        "theme_mode": payload.get("mode"),
        "theme_palette": payload.get("palette"),
        "theme_density": payload.get("density"),
        "theme_text_size": payload.get("textSize") or payload.get("text_size"),
    }
    form = AppearanceForm(data, instance=request.user)
    if form.is_valid():
        form.save()
        return JsonResponse({"ok": True})
    return JsonResponse({"ok": False, "errors": form.errors}, status=400)


@role_required
def activity_log(request):
    entries = AuditLog.objects.select_related("user")
    query = request.GET.get("q", "").strip()
    action = request.GET.get("action", "").strip()
    valid_actions = {choice[0] for choice in AuditLog.ACTION_CHOICES}

    if query:
        entries = entries.filter(
            Q(object_repr__icontains=query)
            | Q(model__icontains=query)
            | Q(user__username__icontains=query)
            | Q(user__full_name__icontains=query)
        )
    if action in valid_actions:
        entries = entries.filter(action=action)

    paginator = Paginator(entries, 50)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "core/activity_log.html",
        {
            "page_obj": page_obj,
            "is_paginated": page_obj.has_other_pages(),
            "query": query,
            "action": action,
            "action_choices": AuditLog.ACTION_CHOICES,
        },
    )


@role_required
def backup_restore(request):
    backups = BackupLog.objects.all()[:20]
    return render(
        request,
        "core/backup_restore.html",
        {
            "backups": backups,
            "backup_count": len(backups),
            "backup_folder": default_backup_folder(),
        },
    )


@require_POST
@role_required
def backup_now(request):
    log = perform_backup(user=request.user, reason="manual")
    if log.result == "ok":
        messages.success(request, f"Backup written to {log.destination_path}.")
    else:
        messages.error(request, f"Backup failed: {log.message}")
    return redirect("backup_restore")


@role_required
def search(request):
    query = request.GET.get("q", "").strip()
    return render(request, "core/search.html", {"query": query})


@require_POST
def lock_session(request):
    logout(request)
    return HttpResponse(status=204)


def setup(request):
    if User.objects.exists():
        return redirect("login")
    form = SetupForm(
        request.POST or None, request.FILES or None
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            app_settings = Settings.load()
            app_settings.company_name = form.cleaned_data["company_name"]
            app_settings.address = form.cleaned_data["address"]
            app_settings.phone = form.cleaned_data["phone"]
            app_settings.email = form.cleaned_data["email"]
            app_settings.kra_pin = form.cleaned_data["kra_pin"]
            if form.cleaned_data["logo"]:
                app_settings.logo = form.cleaned_data["logo"]
            app_settings.letterhead_text = form.cleaned_data["letterhead_text"]
            app_settings.backup_folder = form.cleaned_data["backup_folder"]
            app_settings.default_palette = form.cleaned_data["default_palette"]
            app_settings.brand_color = form.cleaned_data["brand_color"]
            app_settings.full_clean()
            app_settings.save()

            user = User.objects.create_user(
                username=form.cleaned_data["owner_username"],
                password=form.cleaned_data["password1"],
                full_name=form.cleaned_data["owner_full_name"],
                is_staff=True,
                is_superuser=True,
                theme_palette=form.cleaned_data["default_palette"],
            )
            code = generate_recovery_code()
            store_recovery_code(code)
        return render(request, "core/setup_done.html", {"recovery_code": code, "owner": user})
    return render(request, "core/setup.html", {"form": form})


@role_required
def help_page(request):
    return render(
        request,
        "core/help.html",
        {
            "version": django_settings.APP_VERSION,
            "data_dir": django_settings.DATA_DIR,
            "backup_status": backup_status(),
            "recovery_exists": has_recovery_code(),
        },
    )


@role_required
def support_bundle(request):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "version.txt",
            f"Rentals Manager {django_settings.APP_VERSION}\n"
            f"Generated {timezone.now():%Y-%m-%d %H:%M:%S}\n"
            f"Python {platform.python_version()}\n"
            f"Platform {platform.platform()}\n",
        )
        log_file = django_settings.LOG_DIR / "app.log"
        if log_file.exists():
            archive.write(log_file, "logs/app.log")
    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = (
        f'attachment; filename="support-bundle-{timezone.localdate():%Y%m%d}.zip"'
    )
    return response


@require_POST
@role_required
def open_data_folder(request):
    target = str(django_settings.DATA_DIR)
    try:
        if platform.system() == "Windows":
            os.startfile(target)  # type: ignore[attr-defined]
        else:
            import subprocess

            subprocess.Popen(["xdg-open", target])
    except Exception as exc:  # noqa: BLE001
        messages.error(request, f"Could not open the data folder: {exc}")
    else:
        messages.success(request, f"Opened {target}.")
    return redirect("help_page")
