import json

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.views import LoginView, LogoutView
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core.backup import default_backup_folder, perform_backup
from core.forms import AppearanceForm, SettingsForm, StyledAuthenticationForm
from core.models import AuditLog, BackupLog, Settings
from core.permissions import role_required


class AppLoginView(LoginView):
    authentication_form = StyledAuthenticationForm
    template_name = "registration/login.html"
    redirect_authenticated_user = True


class AppLogoutView(LogoutView):
    next_page = "login"


@role_required
def dashboard(request):
    return render(request, "core/dashboard.html")


PLACEHOLDERS = {
    "payments": {
        "title": "Payments",
        "subtitle": "Receipts, allocations, credit, cheque lifecycle and statement import.",
        "icon": "payments",
        "empty_title": "No payments yet",
        "description": "Record payments with an allocation preview, receipts and M-Pesa or bank statement matching in the payments phase.",
        "phase_note": "Phase 4 adds payment allocation, receipts and statement import.",
    },
    "maintenance": {
        "title": "Maintenance",
        "subtitle": "Requests per unit with priority, cost and expense links.",
        "icon": "maintenance",
        "empty_title": "No maintenance requests",
        "description": "Log requests, track status and turn completed work into an expense in the operations phase.",
        "phase_note": "Phase 5 adds maintenance requests, deposits and move-out.",
    },
    "expenses": {
        "title": "Expenses",
        "subtitle": "Spending by category with receipt attachments.",
        "icon": "expenses",
        "empty_title": "No expenses yet",
        "description": "Categories, receipts and expense entry arrive with the operations phase.",
        "phase_note": "Phase 5 adds expense categories and receipt attachments.",
    },
    "reports": {
        "title": "Reports",
        "subtitle": "Arrears, income and expenses, occupancy, statements and tax.",
        "icon": "reports",
        "empty_title": "No reports yet",
        "description": "Reports reconcile with the ledger and export to Excel and PDF. Built after the ledger exists.",
        "phase_note": "Phase 6 adds the reports hub, exports and the overdue reminder list.",
    },
}


def _make_placeholder(key):
    details = PLACEHOLDERS[key]

    @role_required
    def view(request):
        return render(request, "core/placeholder.html", details)

    return view


payments = _make_placeholder("payments")
maintenance = _make_placeholder("maintenance")
expenses = _make_placeholder("expenses")
reports = _make_placeholder("reports")


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
