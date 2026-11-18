"""Billing run, invoices, charges and meter readings."""

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from billing.forms import (
    BillingRunForm,
    ChargeTypeForm,
    LeaseChargeForm,
    MeterReadingForm,
    UtilityTypeForm,
)
from billing.models import (
    ChargeType,
    Invoice,
    LeaseCharge,
    MeterReading,
    UtilityType,
    with_balances,
)
from billing.pdf import build_invoice_pdf, build_invoices_pdf
from billing.services import generate_period, parse_period, preview_period
from core.models import Settings
from core.permissions import role_required
from property.models import Lease


def _redirect_to_run(period, due_date):
    return redirect(
        f"{reverse('billing')}?period={period}&due_date={due_date.isoformat()}"
    )


@role_required
def billing_run(request):
    settings_obj = Settings.load()
    period_value = request.GET.get("period") or timezone.localdate().strftime("%Y-%m")
    due_value = request.GET.get("due_date", "")
    form = BillingRunForm({"period": period_value, "due_date": due_value})

    rows = []
    skipped = 0
    invoice_count = 0
    period_start = None
    period_end = None
    due_date = None
    projected_total = 0

    if form.is_valid():
        period_start = form.period_start
        period_end = form.period_end
        due_date = form.cleaned_data["due_date"]
        rows, skipped = preview_period(period_start, period_end, settings_obj)
        invoice_count = Invoice.objects.filter(period_start=period_start).count()
        projected_total = sum((row["total"] for row in rows), start=0)
    elif request.GET:
        messages.error(request, "Enter a valid period as YYYY-MM.")

    return render(
        request,
        "billing/run.html",
        {
            "form": form,
            "rows": rows,
            "skipped": skipped,
            "invoice_count": invoice_count,
            "period_start": period_start,
            "period_end": period_end,
            "due_date": due_date,
            "projected_total": projected_total,
        },
    )


@require_POST
@role_required
def billing_generate(request):
    form = BillingRunForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Choose a valid period and due date.")
        return redirect("billing")

    lease_ids = request.POST.getlist("lease_ids")
    if not lease_ids:
        messages.warning(request, "Select at least one lease to invoice.")
        return _redirect_to_run(
            form.cleaned_data["period"], form.cleaned_data["due_date"]
        )

    created, skipped = generate_period(
        form.period_start,
        form.period_end,
        form.cleaned_data["due_date"],
        user=request.user,
        lease_ids=lease_ids,
    )
    message = f"{len(created)} invoice(s) generated."
    if skipped:
        message += f" {skipped} skipped because they were already invoiced."
    messages.success(request, message)
    return _redirect_to_run(form.cleaned_data["period"], form.cleaned_data["due_date"])


@role_required
def invoices(request):
    queryset = with_balances(
        Invoice.objects.select_related("tenant", "unit").all()
    )
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    period_value = request.GET.get("period", "").strip()
    period_start = None

    if period_value:
        try:
            period_start, _period_end = parse_period(period_value)
        except ValueError:
            messages.error(request, "Enter a valid period as YYYY-MM.")
        else:
            queryset = queryset.filter(period_start=period_start)
    if query:
        queryset = queryset.filter(
            models_q_number_tenant_unit(query)
        )
    if status in dict(Invoice.STATUS_CHOICES):
        queryset = queryset.filter(status=status)

    invoice_rows = list(queryset)
    return render(
        request,
        "billing/invoices.html",
        {
            "invoices": invoice_rows,
            "query": query,
            "selected_status": status,
            "period_value": period_value,
            "statuses": Invoice.STATUS_CHOICES,
            "counts": {
                "total": len(invoice_rows),
                "value": sum((invoice.total for invoice in invoice_rows), start=0),
            },
        },
    )


def models_q_number_tenant_unit(query):
    from django.db.models import Q

    return (
        Q(invoice_number__icontains=query)
        | Q(tenant__business_name__icontains=query)
        | Q(unit__code__icontains=query)
    )


@role_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related(
            "tenant", "unit", "unit__building", "unit__floor", "lease"
        ),
        pk=pk,
    )
    lines = list(invoice.lines.select_related("charge_type"))
    has_vat = any(line.vat_amount and line.vat_amount != 0 for line in lines)
    allocations = invoice.allocations.filter(payment__status="posted").select_related(
        "payment"
    )
    credit_entries = [
        entry
        for entry in invoice.credit_entries.filter(source="applied_to_invoice")
        if entry.payment is None or entry.payment.status == "posted"
    ]
    return render(
        request,
        "billing/invoice_detail.html",
        {
            "invoice": invoice,
            "lines": lines,
            "has_vat": has_vat,
            "allocations": allocations,
            "credit_entries": credit_entries,
        },
    )


@role_required
def invoice_pdf(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    pdf = build_invoice_pdf(invoice)
    response = HttpResponse(pdf.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{invoice.invoice_number}.pdf"'
    return response


@role_required
def invoice_period_pdf(request):
    period_value = request.GET.get("period") or timezone.localdate().strftime("%Y-%m")
    try:
        period_start, _period_end = parse_period(period_value)
    except ValueError:
        messages.error(request, "Enter a valid period as YYYY-MM.")
        return redirect("invoices")

    invoice_list = list(
        Invoice.objects.filter(period_start=period_start)
        .select_related("tenant", "unit", "unit__building", "unit__floor", "lease")
        .order_by("unit__code", "invoice_number")
    )
    if not invoice_list:
        messages.warning(request, "There are no invoices for that period.")
        return redirect(f"{reverse('invoices')}?period={period_value}")

    pdf = build_invoices_pdf(invoice_list)
    response = HttpResponse(pdf.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="invoices-{period_value}.pdf"'
    return response


@role_required
def charge_types(request):
    form = ChargeTypeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Charge type added.")
        return redirect("charge_types")
    return render(
        request,
        "billing/charge_types.html",
        {"form": form, "charge_types": ChargeType.objects.all()},
    )


@role_required
def charge_type_edit(request, pk):
    charge_type = get_object_or_404(ChargeType, pk=pk)
    form = ChargeTypeForm(request.POST or None, instance=charge_type)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Charge type updated.")
        return redirect("charge_types")
    return render(
        request,
        "billing/charge_type_form.html",
        {"form": form, "title": f"Edit {charge_type.name}"},
    )


@require_POST
@role_required
def charge_type_toggle(request, pk):
    charge_type = get_object_or_404(ChargeType, pk=pk)
    charge_type.is_active = not charge_type.is_active
    charge_type.save(update_fields=["is_active", "updated_at"])
    messages.success(request, "Charge type updated.")
    return redirect("charge_types")


@role_required
def lease_charges(request, lease_pk):
    lease = get_object_or_404(
        Lease.objects.select_related("tenant", "unit"), pk=lease_pk
    )
    form = LeaseChargeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        charge = form.save(commit=False)
        charge.lease = lease
        charge.save()
        messages.success(request, "Lease charge added.")
        return redirect("lease_charges", lease_pk=lease.pk)
    return render(
        request,
        "billing/lease_charges.html",
        {
            "lease": lease,
            "charges": lease.charges.select_related("charge_type"),
            "form": form,
        },
    )


@role_required
def lease_charge_edit(request, pk):
    charge = get_object_or_404(LeaseCharge.objects.select_related("lease"), pk=pk)
    form = LeaseChargeForm(request.POST or None, instance=charge)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Lease charge updated.")
        return redirect("lease_charges", lease_pk=charge.lease_id)
    return render(
        request,
        "billing/lease_charge_form.html",
        {"form": form, "title": "Edit lease charge", "charge": charge},
    )


@require_POST
@role_required
def lease_charge_toggle(request, pk):
    charge = get_object_or_404(LeaseCharge, pk=pk)
    charge.is_active = not charge.is_active
    charge.save(update_fields=["is_active", "updated_at"])
    messages.success(request, "Lease charge updated.")
    return redirect("lease_charges", lease_pk=charge.lease_id)


@role_required
def utility_types(request):
    form = UtilityTypeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Utility type added.")
        return redirect("utility_types")
    return render(
        request,
        "billing/utility_types.html",
        {"form": form, "utility_types": UtilityType.objects.all()},
    )


@role_required
def utility_type_edit(request, pk):
    utility_type = get_object_or_404(UtilityType, pk=pk)
    form = UtilityTypeForm(request.POST or None, instance=utility_type)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Utility type updated.")
        return redirect("utility_types")
    return render(
        request,
        "billing/utility_type_form.html",
        {"form": form, "title": f"Edit {utility_type.name}"},
    )


@require_POST
@role_required
def utility_type_toggle(request, pk):
    utility_type = get_object_or_404(UtilityType, pk=pk)
    utility_type.is_active = not utility_type.is_active
    utility_type.save(update_fields=["is_active", "updated_at"])
    messages.success(request, "Utility type updated.")
    return redirect("utility_types")


@role_required
def meter_readings(request):
    readings = MeterReading.objects.select_related(
        "unit", "utility_type", "invoice_line", "invoice_line__invoice"
    )
    unit_id = request.GET.get("unit", "").strip()
    utility_id = request.GET.get("utility", "").strip()
    billed = request.GET.get("billed", "").strip()
    if unit_id.isdigit():
        readings = readings.filter(unit_id=unit_id)
    if utility_id.isdigit():
        readings = readings.filter(utility_type_id=utility_id)
    if billed == "yes":
        readings = readings.filter(invoice_line__isnull=False)
    elif billed == "no":
        readings = readings.filter(invoice_line__isnull=True)

    form = MeterReadingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        reading = form.save()
        messages.success(request, "Meter reading saved.")
        return redirect("meter_readings")

    from property.models import Unit

    return render(
        request,
        "billing/meter_readings.html",
        {
            "readings": readings,
            "form": form,
            "units": Unit.objects.select_related("building", "floor").order_by("code"),
            "utility_types": UtilityType.objects.all(),
            "selected_unit": unit_id,
            "selected_utility": utility_id,
            "selected_billed": billed,
        },
    )


@role_required
def meter_reading_edit(request, pk):
    reading = get_object_or_404(MeterReading, pk=pk)
    if reading.invoice_line_id:
        messages.error(request, "This reading is already on an invoice and cannot be edited.")
        return redirect("meter_readings")
    form = MeterReadingForm(request.POST or None, instance=reading)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Meter reading updated.")
        return redirect("meter_readings")
    return render(
        request,
        "billing/meter_reading_form.html",
        {"form": form, "title": "Edit meter reading", "reading": reading},
    )


@require_POST
@role_required
def meter_reading_delete(request, pk):
    reading = get_object_or_404(MeterReading, pk=pk)
    if reading.invoice_line_id:
        messages.error(request, "This reading is already on an invoice and cannot be deleted.")
    else:
        reading.delete()
        messages.success(request, "Meter reading deleted.")
    return redirect("meter_readings")
