"""Property, tenant, lease and import screens."""

from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import AuditLog
from core.permissions import role_required
from property.forms import (
    BuildingForm,
    DocumentForm,
    FloorForm,
    ImportForm,
    LeaseForm,
    TenantContactForm,
    TenantForm,
    TerminateLeaseForm,
    UnitForm,
)
from property.import_export import (
    ImportFileError,
    commit_import,
    parse_workbook,
    sample_workbook_bytes,
    template_bytes,
)
from property.models import (
    Building,
    Document,
    Floor,
    Lease,
    Tenant,
    TenantContact,
    Unit,
)
from property.services import (
    refresh_lease_statuses,
    sync_unit_status,
)

OWNER_MODELS = {"tenant": Tenant, "lease": Lease}


def _documents_for(obj):
    content_type = ContentType.objects.get_for_model(obj.__class__)
    return Document.objects.filter(owner_type=content_type, owner_id=obj.pk)


def _safe_next(request, fallback):
    target = request.POST.get("next") or request.GET.get("next")
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return fallback


def _units_with_leases(units):
    today = timezone.localdate()
    leases = (
        Lease.objects.filter(
            status=Lease.STATUS_ACTIVE,
            start_date__lte=today,
        )
        .filter(Q(end_date__gte=today) | Q(end_date__isnull=True))
        .select_related("tenant")
        .order_by("-start_date")
    )
    by_unit = {}
    for lease in leases:
        by_unit.setdefault(lease.unit_id, lease)
    for unit in units:
        unit.current_lease = by_unit.get(unit.pk)
    return units


@role_required
def unit_list(request):
    refresh_lease_statuses()

    units = Unit.objects.select_related("building", "floor")
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    building_id = request.GET.get("building", "").strip()
    floor_id = request.GET.get("floor", "").strip()
    include_inactive = request.GET.get("include_inactive") == "1"

    if not include_inactive:
        units = units.filter(is_active=True)
    if query:
        tenant_unit_ids = Lease.objects.filter(
            tenant__business_name__icontains=query,
            status=Lease.STATUS_ACTIVE,
        ).values("unit_id")
        units = units.filter(
            Q(code__icontains=query)
            | Q(notes__icontains=query)
            | Q(id__in=tenant_unit_ids)
        )
    if status in dict(Unit.STATUS_CHOICES):
        units = units.filter(status=status)
    if building_id.isdigit():
        units = units.filter(building_id=building_id)
    if floor_id.isdigit():
        units = units.filter(floor_id=floor_id)

    unit_rows = list(_units_with_leases(units))
    floor_groups = []
    grouped = {}
    for unit in unit_rows:
        grouped.setdefault(unit.floor, []).append(unit)
    for floor, floor_units in sorted(
        grouped.items(),
        key=lambda item: (
            item[0].building.name,
            item[0].sort_order,
            item[0].name,
        ),
    ):
        floor_groups.append({"floor": floor, "units": floor_units})

    counts = {
        "total": len(unit_rows),
        "occupied": sum(1 for unit in unit_rows if unit.status == Unit.STATUS_OCCUPIED),
        "vacant": sum(1 for unit in unit_rows if unit.status == Unit.STATUS_VACANT),
        "reserved": sum(1 for unit in unit_rows if unit.status == Unit.STATUS_RESERVED),
    }

    view_mode = "grid" if request.GET.get("view") == "grid" else "table"
    context = {
        "units": unit_rows,
        "floor_groups": floor_groups,
        "buildings": Building.objects.all(),
        "floors": Floor.objects.select_related("building"),
        "statuses": Unit.STATUS_CHOICES,
        "query": query,
        "selected_status": status,
        "selected_building": building_id,
        "selected_floor": floor_id,
        "include_inactive": include_inactive,
        "view_mode": view_mode,
        "counts": counts,
    }
    return render(request, "property/unit_list.html", context)


@role_required
def unit_create(request):
    form = UnitForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        unit = form.save()
        sync_unit_status(unit)
        messages.success(request, f"Unit {unit.code} created.")
        return redirect("unit_detail", pk=unit.pk)
    return render(request, "property/unit_form.html", {"form": form, "title": "New unit"})


@role_required
def unit_detail(request, pk):
    unit = get_object_or_404(
        Unit.objects.select_related("building", "floor"), pk=pk
    )
    refresh_lease_statuses()
    unit.refresh_from_db()
    leases = unit.leases.select_related("tenant").order_by("-start_date")
    tenants = (
        Tenant.objects.filter(Q(primary_unit=unit) | Q(leases__unit=unit))
        .distinct()
        .order_by("business_name")
    )
    return render(
        request,
        "property/unit_detail.html",
        {
            "unit": unit,
            "current_lease": unit.active_lease,
            "leases": leases,
            "tenants": tenants,
        },
    )


@role_required
def unit_edit(request, pk):
    unit = get_object_or_404(Unit, pk=pk)
    form = UnitForm(request.POST or None, instance=unit)
    if request.method == "POST" and form.is_valid():
        unit = form.save()
        sync_unit_status(unit)
        messages.success(request, f"Unit {unit.code} updated.")
        return redirect("unit_detail", pk=unit.pk)
    return render(
        request,
        "property/unit_form.html",
        {"form": form, "title": f"Edit unit {unit.code}", "unit": unit},
    )


@require_POST
@role_required
def unit_toggle_active(request, pk):
    unit = get_object_or_404(Unit, pk=pk)
    if unit.is_active:
        if Lease.objects.filter(unit=unit, status=Lease.STATUS_ACTIVE).exists():
            messages.error(request, "End or terminate the unit's active lease before archiving it.")
            return redirect("unit_detail", pk=unit.pk)
        unit.is_active = False
        unit.save(update_fields=["is_active", "updated_at"])
        messages.success(request, f"Unit {unit.code} archived.")
    else:
        unit.is_active = True
        unit.save(update_fields=["is_active", "updated_at"])
        messages.success(request, f"Unit {unit.code} restored.")
    return redirect("unit_detail", pk=unit.pk)


@require_POST
@role_required
def unit_delete(request, pk):
    unit = get_object_or_404(Unit, pk=pk)
    unit_pk = unit.pk
    code = unit.code
    try:
        with transaction.atomic():
            unit.delete()
    except ProtectedError:
        messages.error(
            request,
            f"Unit {code} has leases, invoices or other records. Remove those "
            "first, or archive the unit instead.",
        )
        return redirect("unit_detail", pk=unit_pk)
    messages.success(request, f"Unit {code} deleted.")
    return redirect("units")


@role_required
def building_list(request):
    form = BuildingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        building = form.save()
        messages.success(request, f"Building {building.name} created.")
        return redirect("building_detail", pk=building.pk)
    buildings = Building.objects.prefetch_related("floors", "units")
    return render(
        request,
        "property/building_list.html",
        {"buildings": buildings, "form": form},
    )


@role_required
def building_detail(request, pk):
    building = get_object_or_404(Building, pk=pk)
    floor_form = FloorForm(request.POST or None, initial={"building": building})
    if request.method == "POST" and floor_form.is_valid():
        floor = floor_form.save()
        messages.success(request, f"Floor {floor.name} created.")
        return redirect("building_detail", pk=building.pk)
    floors = building.floors.prefetch_related("units")
    return render(
        request,
        "property/building_detail.html",
        {"building": building, "floors": floors, "floor_form": floor_form},
    )


@role_required
def building_edit(request, pk):
    building = get_object_or_404(Building, pk=pk)
    form = BuildingForm(request.POST or None, instance=building)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Building updated.")
        return redirect("building_detail", pk=building.pk)
    return render(
        request,
        "property/building_form.html",
        {"form": form, "title": f"Edit {building.name}", "building": building},
    )


@require_POST
@role_required
def building_delete(request, pk):
    building = get_object_or_404(Building, pk=pk)
    if building.units.exists() or building.floors.exists():
        messages.error(request, "Delete the building's floors and units first.")
        return redirect("building_detail", pk=building.pk)
    name = building.name
    building.delete()
    messages.success(request, f"Building {name} deleted.")
    return redirect("buildings")


@role_required
def floor_edit(request, pk):
    floor = get_object_or_404(Floor, pk=pk)
    form = FloorForm(request.POST or None, instance=floor)
    if request.method == "POST" and form.is_valid():
        floor = form.save()
        messages.success(request, "Floor updated.")
        return redirect("building_detail", pk=floor.building_id)
    return render(
        request,
        "property/floor_form.html",
        {"form": form, "title": f"Edit {floor.name}", "floor": floor},
    )


@require_POST
@role_required
def floor_delete(request, pk):
    floor = get_object_or_404(Floor, pk=pk)
    building_id = floor.building_id
    if floor.units.exists():
        messages.error(request, "Move or delete the floor's units first.")
        return redirect("building_detail", pk=building_id)
    floor.delete()
    messages.success(request, "Floor deleted.")
    return redirect("building_detail", pk=building_id)


@role_required
def tenant_list(request):
    refresh_lease_statuses()
    tenants = Tenant.objects.select_related("primary_unit").prefetch_related("contacts")
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    if query:
        tenants = tenants.filter(
            Q(business_name__icontains=query)
            | Q(trade__icontains=query)
            | Q(id_or_kra_pin__icontains=query)
            | Q(primary_unit__code__icontains=query)
            | Q(contacts__name__icontains=query)
            | Q(contacts__phone__icontains=query)
        ).distinct()
    if status in dict(Tenant.STATUS_CHOICES):
        tenants = tenants.filter(status=status)

    tenant_rows = list(tenants)
    today = timezone.localdate()
    active_by_tenant = {
        lease.tenant_id: lease
        for lease in Lease.objects.filter(
            status=Lease.STATUS_ACTIVE,
            start_date__lte=today,
        )
        .filter(Q(end_date__gte=today) | Q(end_date__isnull=True))
        .select_related("unit")
    }
    for tenant in tenant_rows:
        lease = active_by_tenant.get(tenant.pk)
        tenant.display_unit = tenant.primary_unit or (lease.unit if lease else None)
    return render(
        request,
        "property/tenant_list.html",
        {
            "tenants": tenant_rows,
            "statuses": Tenant.STATUS_CHOICES,
            "query": query,
            "selected_status": status,
            "counts": {
                "total": len(tenant_rows),
                "active": sum(1 for t in tenant_rows if t.status == Tenant.STATUS_ACTIVE),
                "former": sum(1 for t in tenant_rows if t.status == Tenant.STATUS_FORMER),
                "leases": len(active_by_tenant),
            },
        },
    )


@role_required
def tenant_create(request):
    form = TenantForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        tenant = form.save()
        messages.success(
            request,
            f"Tenant {tenant.business_name} created. Choose a lease type to "
            "assign their shop.",
        )
        return redirect(f"{reverse('lease_create')}?tenant={tenant.pk}")
    return render(request, "property/tenant_form.html", {"form": form, "title": "New tenant"})


@role_required
def tenant_detail(request, pk):
    refresh_lease_statuses()
    tenant = get_object_or_404(Tenant.objects.select_related("primary_unit"), pk=pk)
    tab = request.GET.get("tab", "overview")
    if tab not in {"overview", "lease", "statement", "payments", "documents", "notes"}:
        tab = "overview"

    leases = tenant.leases.select_related("unit").order_by("-start_date")
    contacts = tenant.contacts.all()
    documents = _documents_for(tenant)
    current_lease = tenant.current_lease
    invoices = tenant.invoices.filter(status="issued").select_related("unit").order_by(
        "issue_date", "id"
    )
    payments = tenant.payments.filter(status="posted").select_related().order_by(
        "date_received", "id"
    )

    events = []
    for invoice in invoices:
        events.append(
            {
                "date": invoice.issue_date,
                "order": 1,
                "description": f"Invoice {invoice.invoice_number}",
                "invoice": invoice,
                "charged": invoice.total,
                "paid": None,
            }
        )
    for payment in payments:
        events.append(
            {
                "date": payment.date_received,
                "order": 2,
                "description": f"Receipt {payment.receipt_number}",
                "payment": payment,
                "charged": None,
                "paid": payment.settlement_amount,
            }
        )
    events.sort(key=lambda event: (event["date"], event["order"]))
    running = 0
    for event in events:
        running += event["charged"] or 0
        running -= event["paid"] or 0
        event["balance"] = running

    return render(
        request,
        "property/tenant_detail.html",
        {
            "tenant": tenant,
            "tab": tab,
            "leases": leases,
            "contacts": contacts,
            "documents": documents,
            "current_lease": current_lease,
            "invoices": list(invoices),
            "payments": list(payments),
            "statement_events": events,
            "contact_form": TenantContactForm(),
            "document_form": DocumentForm(),
        },
    )


@role_required
def tenant_edit(request, pk):
    tenant = get_object_or_404(Tenant, pk=pk)
    form = TenantForm(request.POST or None, instance=tenant)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Tenant updated.")
        return redirect("tenant_detail", pk=tenant.pk)
    return render(
        request,
        "property/tenant_form.html",
        {"form": form, "title": f"Edit {tenant.business_name}", "tenant": tenant},
    )


@require_POST
@role_required
def tenant_toggle_status(request, pk):
    tenant = get_object_or_404(Tenant, pk=pk)
    if tenant.status == Tenant.STATUS_ACTIVE:
        if Lease.objects.filter(tenant=tenant, status=Lease.STATUS_ACTIVE).exists():
            messages.error(request, "End the tenant's active lease before archiving them.")
            return redirect("tenant_detail", pk=tenant.pk)
        tenant.status = Tenant.STATUS_FORMER
        tenant.save(update_fields=["status", "updated_at"])
        messages.success(request, f"{tenant.business_name} marked as former.")
    else:
        tenant.status = Tenant.STATUS_ACTIVE
        tenant.save(update_fields=["status", "updated_at"])
        messages.success(request, f"{tenant.business_name} restored to active.")
    return redirect("tenant_detail", pk=tenant.pk)


@require_POST
@role_required
def tenant_delete(request, pk):
    tenant = get_object_or_404(Tenant, pk=pk)
    tenant_pk = tenant.pk
    name = tenant.business_name
    documents = list(_documents_for(tenant))
    storage_files = [document.file for document in documents]
    try:
        with transaction.atomic():
            tenant.delete()
            for document in documents:
                document.delete()
    except ProtectedError:
        messages.error(
            request,
            f"{name} has leases, invoices or payments. Terminate the lease and "
            "keep the records, or archive the tenant instead.",
        )
        return redirect("tenant_detail", pk=tenant_pk)
    for storage_file in storage_files:
        storage_file.delete(save=False)
    messages.success(request, f"Tenant {name} deleted.")
    return redirect("tenants")


@require_POST
@role_required
def contact_create(request, pk):
    tenant = get_object_or_404(Tenant, pk=pk)
    form = TenantContactForm(request.POST)
    if form.is_valid():
        contact = form.save(commit=False)
        contact.tenant = tenant
        contact.save()
        messages.success(request, f"Contact {contact.name} added.")
    else:
        messages.error(request, "Check the contact details and try again.")
    return redirect(reverse("tenant_detail", kwargs={"pk": tenant.pk}) + "?tab=overview#contacts")


@role_required
def contact_edit(request, pk):
    contact = get_object_or_404(TenantContact, pk=pk)
    form = TenantContactForm(request.POST or None, instance=contact)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Contact updated.")
        return redirect(
            reverse("tenant_detail", kwargs={"pk": contact.tenant_id}) + "?tab=overview#contacts"
        )
    return render(
        request,
        "property/contact_form.html",
        {"form": form, "title": f"Edit {contact.name}", "contact": contact},
    )


@require_POST
@role_required
def contact_delete(request, pk):
    contact = get_object_or_404(TenantContact, pk=pk)
    tenant_id = contact.tenant_id
    contact.delete()
    messages.success(request, "Contact removed.")
    return redirect(reverse("tenant_detail", kwargs={"pk": tenant_id}) + "?tab=overview#contacts")


@require_POST
@role_required
def document_upload(request):
    owner_type = request.POST.get("owner_type", "")
    model = OWNER_MODELS.get(owner_type)
    if model is None:
        messages.error(request, "Unknown document owner.")
        return redirect("tenants")
    owner = get_object_or_404(model, pk=request.POST.get("owner_id"))
    form = DocumentForm(request.POST, request.FILES)
    fallback = (
        reverse("tenant_detail", kwargs={"pk": owner.pk}) + "?tab=documents"
        if isinstance(owner, Tenant)
        else reverse("lease_detail", kwargs={"pk": owner.pk})
    )
    if form.is_valid():
        document = form.save(commit=False)
        document.owner_type = ContentType.objects.get_for_model(model)
        document.owner_id = owner.pk
        document.uploaded_by = request.user
        document.save()
        messages.success(request, "Document uploaded.")
    else:
        messages.error(request, "Choose a document type and a valid file.")
    return redirect(_safe_next(request, fallback))


@require_POST
@role_required
def document_delete(request, pk):
    document = get_object_or_404(Document, pk=pk)
    owner = document.content_object
    if isinstance(owner, Tenant):
        fallback = reverse("tenant_detail", kwargs={"pk": owner.pk}) + "?tab=documents"
    elif isinstance(owner, Lease):
        fallback = reverse("lease_detail", kwargs={"pk": owner.pk})
    else:
        fallback = reverse("tenants")
    storage_file = document.file
    document.delete()
    storage_file.delete(save=False)
    messages.success(request, "Document deleted.")
    return redirect(_safe_next(request, fallback))


@role_required
def lease_list(request):
    refresh_lease_statuses()
    leases = Lease.objects.select_related("tenant", "unit", "unit__building")
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    if query:
        leases = leases.filter(
            Q(tenant__business_name__icontains=query)
            | Q(unit__code__icontains=query)
            | Q(unit__building__name__icontains=query)
        )
    if status in dict(Lease.STATUS_CHOICES):
        leases = leases.filter(status=status)
    lease_rows = list(leases)
    return render(
        request,
        "property/lease_list.html",
        {
            "leases": lease_rows,
            "statuses": Lease.STATUS_CHOICES,
            "query": query,
            "selected_status": status,
            "counts": {
                "total": len(lease_rows),
                "active": sum(1 for l in lease_rows if l.status == Lease.STATUS_ACTIVE),
                "draft": sum(1 for l in lease_rows if l.status == Lease.STATUS_DRAFT),
                "expired": sum(1 for l in lease_rows if l.status == Lease.STATUS_EXPIRED),
            },
        },
    )


@role_required
def lease_create(request):
    initial = {}
    tenant_obj = None
    tenant_id = request.GET.get("tenant")
    unit_id = request.GET.get("unit")
    agreement_type = request.GET.get("agreement_type")
    if agreement_type in dict(Lease.AGREEMENT_CHOICES):
        initial["agreement_type"] = agreement_type
    if tenant_id and tenant_id.isdigit():
        tenant_obj = (
            Tenant.objects.select_related("primary_unit").filter(pk=tenant_id).first()
        )
        if tenant_obj:
            initial["tenant"] = tenant_obj
            if not unit_id and tenant_obj.primary_unit_id:
                initial["unit"] = tenant_obj.primary_unit
                initial["monthly_rent"] = tenant_obj.primary_unit.base_rent
    if unit_id and unit_id.isdigit():
        initial["unit"] = unit_id
        unit = Unit.objects.filter(pk=unit_id).first()
        if unit:
            initial["monthly_rent"] = unit.base_rent
    form = LeaseForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        lease = form.save()
        messages.success(request, "Lease created.")
        return redirect("lease_detail", pk=lease.pk)
    cancel_url = (
        reverse("tenant_detail", kwargs={"pk": tenant_obj.pk})
        if tenant_obj
        else reverse("leases")
    )
    return render(
        request,
        "property/lease_form.html",
        {
            "form": form,
            "title": "New lease / monthly rental",
            "cancel_url": cancel_url,
            "tenant_context": tenant_obj,
        },
    )


@role_required
def lease_detail(request, pk):
    refresh_lease_statuses()
    lease = get_object_or_404(
        Lease.objects.select_related("tenant", "unit", "unit__building", "unit__floor"),
        pk=pk,
    )
    rent_history = lease.rent_history.select_related("changed_by")
    audit_entries = AuditLog.objects.filter(
        model="property.Lease", object_id=str(lease.pk)
    ).select_related("user")[:20]
    documents = _documents_for(lease)
    return render(
        request,
        "property/lease_detail.html",
        {
            "lease": lease,
            "rent_history": rent_history,
            "audit_entries": audit_entries,
            "documents": documents,
            "document_form": DocumentForm(),
            "terminate_form": TerminateLeaseForm(),
        },
    )


@role_required
def lease_edit(request, pk):
    lease = get_object_or_404(Lease, pk=pk)
    form = LeaseForm(request.POST or None, instance=lease)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Lease updated.")
        return redirect("lease_detail", pk=lease.pk)
    return render(
        request,
        "property/lease_form.html",
        {"form": form, "title": f"Edit lease - {lease.unit.code}", "lease": lease},
    )


@require_POST
@role_required
def lease_terminate(request, pk):
    lease = get_object_or_404(Lease, pk=pk)
    if lease.status == Lease.STATUS_TERMINATED:
        messages.info(request, "This lease is already terminated.")
        return redirect("lease_detail", pk=lease.pk)
    form = TerminateLeaseForm(request.POST)
    if form.is_valid():
        lease.status = Lease.STATUS_TERMINATED
        lease.terminated_on = form.cleaned_data["terminated_on"]
        lease.termination_reason = form.cleaned_data["termination_reason"]
        lease.save(update_fields=["status", "terminated_on", "termination_reason", "updated_at"])
        messages.success(request, "Lease terminated.")
    else:
        messages.error(request, "Check the termination date.")
    return redirect("lease_detail", pk=lease.pk)


@role_required
def import_data(request):
    form = ImportForm()
    preview = None
    counts = None
    committed = False

    if request.method == "POST":
        form = ImportForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                refresh_lease_statuses()
                preview = parse_workbook(form.cleaned_data["file"])
                if preview.errors:
                    messages.error(
                        request,
                        f"{len(preview.errors)} row error(s). Nothing was imported.",
                    )
                elif preview.total_rows == 0:
                    messages.warning(request, "The workbook has no data rows.")
                else:
                    counts = commit_import(preview)
                    committed = True
                    messages.success(request, "Import complete.")
                    form = ImportForm()
            except ImportFileError as exc:
                messages.error(request, str(exc))
            except (ValidationError, IntegrityError) as exc:
                messages.error(request, f"Import failed and was rolled back: {exc}")

    return render(
        request,
        "property/import.html",
        {
            "form": form,
            "preview": preview,
            "counts": counts,
            "committed": committed,
        },
    )


@role_required
def import_template(request):
    response = HttpResponse(
        template_bytes(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="rentals-import-template.xlsx"'
    return response


@role_required
def import_sample(request):
    response = HttpResponse(
        sample_workbook_bytes(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="rentals-sample-40.xlsx"'
    return response
