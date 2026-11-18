"""Deposits, move-outs, prospects, maintenance and expenses."""

from datetime import timedelta

from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from billing.models import UtilityType
from core.permissions import role_required
from operations.forms import (
    DepositForm,
    ExpenseCategoryForm,
    ExpenseForm,
    MaintenanceRequestForm,
    MoveOutForm,
    MoveOutItemFormSet,
    ProspectForm,
)
from operations.models import (
    Deposit,
    Expense,
    ExpenseCategory,
    MaintenanceRequest,
    MoveOut,
    MoveOutItem,
    Prospect,
)
from operations.pdf import build_move_out_pdf
from billing.services import add_months
from operations.services import (
    compute_move_out,
    create_move_out,
    record_deposit,
    record_final_readings,
    settle_move_out,
)
from property.forms import DocumentForm, LeaseForm
from property.models import Document, Lease, Tenant, TenantContact, Unit
from property.services import refresh_lease_statuses


def _documents_for(obj):
    content_type = ContentType.objects.get_for_model(obj.__class__)
    return Document.objects.filter(owner_type=content_type, owner_id=obj.pk)


@role_required
def lease_deposits(request, lease_pk):
    lease = get_object_or_404(
        Lease.objects.select_related("tenant", "unit"), pk=lease_pk
    )
    form = DepositForm(
        request.POST or None,
        initial={"amount_received": lease.deposit_amount},
    )
    if request.method == "POST" and form.is_valid():
        try:
            deposit = record_deposit(
                lease,
                form.cleaned_data["amount_received"],
                form.cleaned_data["received_date"],
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f"Deposit {deposit.amount_received} recorded.")
            return redirect("lease_deposits", lease_pk=lease.pk)
    return render(
        request,
        "operations/deposits.html",
        {
            "lease": lease,
            "deposits": lease.deposits.all(),
            "form": form,
        },
    )


@role_required
def move_outs(request):
    refresh_lease_statuses()
    queryset = MoveOut.objects.select_related(
        "lease", "lease__tenant", "lease__unit"
    )
    status = request.GET.get("status", "").strip()
    if status in dict(MoveOut.STATUS_CHOICES):
        queryset = queryset.filter(status=status)
    rows = list(queryset)
    return render(
        request,
        "operations/move_outs.html",
        {
            "move_outs": rows,
            "statuses": MoveOut.STATUS_CHOICES,
            "selected_status": status,
        },
    )


@role_required
def move_out_create(request, lease_pk):
    lease = get_object_or_404(
        Lease.objects.select_related("tenant", "unit"), pk=lease_pk
    )
    planned = lease.move_outs.filter(status=MoveOut.STATUS_PLANNED).first()
    if planned:
        messages.info(request, "This lease already has a planned move-out.")
        return redirect("move_out_detail", pk=planned.pk)

    utility_types = UtilityType.objects.filter(is_active=True)
    today = timezone.localdate()
    form = MoveOutForm(
        request.POST or None,
        utility_types=utility_types,
        lease=lease,
        initial={"move_out_date": today, "notice_date": today},
    )
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                move_out = create_move_out(
                    lease,
                    form.cleaned_data["move_out_date"],
                    form.cleaned_data["notice_date"],
                    form.cleaned_data["settlement_notes"],
                )
                record_final_readings(
                    lease,
                    form.cleaned_data["move_out_date"],
                    form.reading_values(),
                )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Move-out planned.")
            return redirect("move_out_detail", pk=move_out.pk)

    return render(
        request,
        "operations/move_out_form.html",
        {"lease": lease, "form": form, "utility_types": utility_types},
    )


@role_required
def move_out_detail(request, pk):
    move_out = get_object_or_404(
        MoveOut.objects.select_related(
            "lease", "lease__tenant", "lease__unit"
        ),
        pk=pk,
    )
    compute_move_out(move_out)
    formset = MoveOutItemFormSet(
        request.POST if request.method == "POST" else None,
        instance=move_out,
    )
    if request.method == "POST" and formset.is_valid():
        formset.save()
        compute_move_out(move_out)
        messages.success(request, "Checklist saved.")
        return redirect("move_out_detail", pk=move_out.pk)

    readings = (
        move_out.lease.unit.meter_readings.filter(
            reading_date=move_out.move_out_date
        )
        .select_related("utility_type")
        .order_by("utility_type__name")
    )
    return render(
        request,
        "operations/move_out_detail.html",
        {
            "move_out": move_out,
            "formset": formset,
            "readings": readings,
            "deposits": move_out.lease.deposits.all(),
        },
    )


@require_POST
@role_required
def move_out_settle(request, pk):
    move_out = get_object_or_404(MoveOut, pk=pk)
    settle_move_out(move_out, user=request.user)
    messages.success(request, "Move-out settled; lease terminated and unit freed.")
    return redirect("move_out_detail", pk=move_out.pk)


@role_required
def move_out_pdf(request, pk):
    move_out = get_object_or_404(
        MoveOut.objects.select_related(
            "lease", "lease__tenant", "lease__unit"
        ),
        pk=pk,
    )
    compute_move_out(move_out)
    pdf = build_move_out_pdf(move_out)
    response = HttpResponse(pdf.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="move-out-{move_out.lease.unit.code}-{move_out.move_out_date}.pdf"'
    )
    return response


@role_required
def prospects(request):
    refresh_lease_statuses()
    queryset = Prospect.objects.select_related("interested_unit")
    status = request.GET.get("status", "").strip()
    query = request.GET.get("q", "").strip()
    if status in dict(Prospect.STATUS_CHOICES):
        queryset = queryset.filter(status=status)
    if query:
        from django.db.models import Q

        queryset = queryset.filter(
            Q(name__icontains=query)
            | Q(business__icontains=query)
            | Q(phone__icontains=query)
        )
    rows = list(queryset)
    vacant_units = (
        Unit.objects.filter(is_active=True, status=Unit.STATUS_VACANT)
        .select_related("building", "floor")
        .order_by("code")
    )
    return render(
        request,
        "operations/prospects.html",
        {
            "prospects": rows,
            "vacant_units": vacant_units,
            "statuses": Prospect.STATUS_CHOICES,
            "selected_status": status,
            "query": query,
            "today": timezone.localdate(),
            "counts": {
                "total": len(rows),
                "vacant": vacant_units.count(),
                "follow_up": sum(
                    1
                    for prospect in rows
                    if prospect.follow_up_date
                    and prospect.follow_up_date <= timezone.localdate()
                    and prospect.status not in (Prospect.STATUS_CONVERTED, Prospect.STATUS_LOST)
                ),
            },
        },
    )


@role_required
def prospect_create(request):
    initial = {}
    unit_id = request.GET.get("unit")
    if unit_id and str(unit_id).isdigit():
        unit = Unit.objects.filter(pk=unit_id).first()
        if unit:
            initial["interested_unit"] = unit
            initial["status"] = Prospect.STATUS_VIEWING
    form = ProspectForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        prospect = form.save()
        messages.success(request, "Prospect added.")
        return redirect("prospects")
    return render(
        request,
        "operations/prospect_form.html",
        {"form": form, "title": "New prospect"},
    )


@role_required
def prospect_edit(request, pk):
    prospect = get_object_or_404(Prospect, pk=pk)
    form = ProspectForm(request.POST or None, instance=prospect)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Prospect updated.")
        return redirect("prospects")
    return render(
        request,
        "operations/prospect_form.html",
        {"form": form, "title": f"Edit {prospect}", "prospect": prospect},
    )


@role_required
def prospect_convert(request, pk):
    prospect = get_object_or_404(
        Prospect.objects.select_related("interested_unit"), pk=pk
    )
    if prospect.status == Prospect.STATUS_CONVERTED and prospect.converted_lease_id:
        messages.info(request, "This prospect is already converted.")
        return redirect("lease_detail", pk=prospect.converted_lease_id)

    today = timezone.localdate()
    initial = {
        "start_date": today,
        "end_date": add_months(today, 12) - timedelta(days=1),
        "status": Lease.STATUS_ACTIVE,
    }
    if prospect.interested_unit:
        initial["unit"] = prospect.interested_unit
        initial["monthly_rent"] = prospect.interested_unit.base_rent

    form = LeaseForm(request.POST or None, initial=initial) if request.method == "POST" else LeaseForm(initial=initial)
    if request.method == "POST":
        try:
            with transaction.atomic():
                business_name = prospect.business or prospect.name
                tenant = Tenant.objects.filter(business_name=business_name).first()
                if tenant is None:
                    tenant = Tenant.objects.create(
                        business_name=business_name, trade="", status=Tenant.STATUS_ACTIVE
                    )
                    if prospect.phone or prospect.email:
                        TenantContact.objects.create(
                            tenant=tenant,
                            name=prospect.name,
                            phone=prospect.phone,
                            email=prospect.email,
                            is_primary=True,
                        )
                elif tenant.status != Tenant.STATUS_ACTIVE:
                    tenant.status = Tenant.STATUS_ACTIVE
                    tenant.save(update_fields=["status", "updated_at"])
                post = request.POST.copy()
                post["tenant"] = tenant.pk
                form = LeaseForm(post)
                if not form.is_valid():
                    transaction.set_rollback(True)
                else:
                    lease = form.save()
                    prospect.status = Prospect.STATUS_CONVERTED
                    prospect.converted_lease = lease
                    prospect.save(
                        update_fields=["status", "converted_lease", "updated_at"]
                    )
                    messages.success(request, "Prospect converted to a lease.")
                    return redirect("lease_detail", pk=lease.pk)
        except ValidationError as exc:
            form.add_error(None, exc)

    return render(
        request,
        "operations/prospect_convert.html",
        {"prospect": prospect, "form": form},
    )


@role_required
def maintenance(request):
    queryset = MaintenanceRequest.objects.select_related("unit", "tenant")
    status = request.GET.get("status", "").strip()
    priority = request.GET.get("priority", "").strip()
    if status in dict(MaintenanceRequest.STATUS_CHOICES):
        queryset = queryset.filter(status=status)
    if priority in dict(MaintenanceRequest.PRIORITY_CHOICES):
        queryset = queryset.filter(priority=priority)
    rows = list(queryset)
    return render(
        request,
        "operations/maintenance.html",
        {
            "requests": rows,
            "statuses": MaintenanceRequest.STATUS_CHOICES,
            "priorities": MaintenanceRequest.PRIORITY_CHOICES,
            "selected_status": status,
            "selected_priority": priority,
            "counts": {
                "total": len(rows),
                "open": sum(1 for row in rows if row.status != "done"),
                "urgent": sum(
                    1
                    for row in rows
                    if row.priority == MaintenanceRequest.PRIORITY_URGENT
                    and row.status != "done"
                ),
            },
        },
    )


@role_required
def maintenance_create(request):
    form = MaintenanceRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        request_obj = form.save()
        messages.success(request, "Maintenance request created.")
        return redirect("maintenance_detail", pk=request_obj.pk)
    return render(
        request,
        "operations/maintenance_form.html",
        {"form": form, "title": "New maintenance request"},
    )


@role_required
def maintenance_detail(request, pk):
    request_obj = get_object_or_404(
        MaintenanceRequest.objects.select_related("unit", "tenant", "expense"), pk=pk
    )
    return render(
        request,
        "operations/maintenance_detail.html",
        {"request_obj": request_obj},
    )


@role_required
def maintenance_edit(request, pk):
    request_obj = get_object_or_404(MaintenanceRequest, pk=pk)
    form = MaintenanceRequestForm(request.POST or None, instance=request_obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Maintenance request updated.")
        return redirect("maintenance_detail", pk=request_obj.pk)
    return render(
        request,
        "operations/maintenance_form.html",
        {"form": form, "title": "Edit maintenance request", "request_obj": request_obj},
    )


@role_required
def expenses(request):
    queryset = Expense.objects.select_related("category", "maintenance_request")
    category_id = request.GET.get("category", "").strip()
    query = request.GET.get("q", "").strip()
    if category_id.isdigit():
        queryset = queryset.filter(category_id=category_id)
    if query:
        from django.db.models import Q

        queryset = queryset.filter(
            Q(payee__icontains=query)
            | Q(description__icontains=query)
            | Q(reference__icontains=query)
        )
    rows = list(queryset)
    return render(
        request,
        "operations/expenses.html",
        {
            "expenses": rows,
            "categories": ExpenseCategory.objects.all(),
            "selected_category": category_id,
            "query": query,
            "counts": {
                "total": len(rows),
                "value": sum((expense.amount for expense in rows), start=0),
            },
        },
    )


@role_required
def expense_create(request):
    initial = {}
    maintenance_id = request.GET.get("maintenance")
    maintenance_request = None
    if maintenance_id and str(maintenance_id).isdigit():
        maintenance_request = MaintenanceRequest.objects.filter(
            pk=maintenance_id
        ).first()
        if maintenance_request:
            initial = {
                "maintenance_request": maintenance_request,
                "amount": maintenance_request.cost,
                "description": maintenance_request.title,
                "expense_date": timezone.localdate(),
            }
    form = ExpenseForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        expense = form.save()
        if expense.maintenance_request_id:
            linked = expense.maintenance_request
            linked.expense = expense
            if linked.status != MaintenanceRequest.STATUS_DONE:
                linked.status = MaintenanceRequest.STATUS_DONE
                linked.completed_date = linked.completed_date or timezone.localdate()
            linked.save(
                update_fields=["expense", "status", "completed_date", "updated_at"]
            )
        messages.success(request, "Expense recorded.")
        return redirect("expense_detail", pk=expense.pk)
    return render(
        request,
        "operations/expense_form.html",
        {"form": form, "title": "New expense"},
    )


@role_required
def expense_detail(request, pk):
    expense = get_object_or_404(
        Expense.objects.select_related("category", "maintenance_request"), pk=pk
    )
    return render(
        request,
        "operations/expense_detail.html",
        {
            "expense": expense,
            "documents": _documents_for(expense),
            "document_form": DocumentForm(),
        },
    )


@role_required
def expense_edit(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    form = ExpenseForm(request.POST or None, instance=expense)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Expense updated.")
        return redirect("expense_detail", pk=expense.pk)
    return render(
        request,
        "operations/expense_form.html",
        {"form": form, "title": "Edit expense", "expense": expense},
    )


@require_POST
@role_required
def expense_receipt_upload(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    form = DocumentForm(request.POST, request.FILES)
    if form.is_valid():
        document = form.save(commit=False)
        document.owner_type = ContentType.objects.get_for_model(Expense)
        document.owner_id = expense.pk
        document.uploaded_by = request.user
        document.save()
        messages.success(request, "Receipt uploaded.")
    else:
        messages.error(request, "Choose a document type and a valid file.")
    return redirect("expense_detail", pk=expense.pk)


@require_POST
@role_required
def expense_receipt_delete(request, pk):
    document = get_object_or_404(Document, pk=pk)
    expense_type = ContentType.objects.get_for_model(Expense)
    if document.owner_type_id != expense_type.pk:
        messages.error(request, "That document is not an expense receipt.")
        return redirect("expenses")
    expense_id = document.owner_id
    storage_file = document.file
    document.delete()
    storage_file.delete(save=False)
    messages.success(request, "Receipt deleted.")
    return redirect("expense_detail", pk=expense_id)


@role_required
def expense_categories(request):
    form = ExpenseCategoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Expense category added.")
        return redirect("expense_categories")
    return render(
        request,
        "operations/expense_categories.html",
        {"form": form, "categories": ExpenseCategory.objects.all()},
    )


@role_required
def expense_category_edit(request, pk):
    category = get_object_or_404(ExpenseCategory, pk=pk)
    form = ExpenseCategoryForm(request.POST or None, instance=category)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Expense category updated.")
        return redirect("expense_categories")
    return render(
        request,
        "operations/expense_category_form.html",
        {"form": form, "title": f"Edit {category.name}"},
    )


@require_POST
@role_required
def expense_category_toggle(request, pk):
    category = get_object_or_404(ExpenseCategory, pk=pk)
    category.is_active = not category.is_active
    category.save(update_fields=["is_active", "updated_at"])
    messages.success(request, "Expense category updated.")
    return redirect("expense_categories")
