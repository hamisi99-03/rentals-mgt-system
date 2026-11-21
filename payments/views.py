"""Payment recording, receipts, cheque lifecycle and statement imports."""

from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from billing.models import Invoice
from core.permissions import role_required
from payments.forms import PaymentForm, StatementImportForm
from payments.import_statements import (
    StatementImportError,
    confirm_row,
    create_import,
    ignore_row,
)
from payments.models import Payment, StatementImport, StatementRow
from payments.pdf import build_receipt_pdf
from payments.services import (
    mark_cheque_banked,
    mark_cheque_bounced,
    record_payment,
    suggest_allocations,
    tenant_account_summary,
    void_payment,
)
from payments.thermal import build_thermal_receipt
from property.models import Tenant


def _decimal(value):
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _has_withholding(raw):
    value = raw.get("has_withholding")
    return str(value).lower() in ("on", "true", "1", "yes")


def _preview_values(raw):
    tenant_id = raw.get("tenant")
    tenant = (
        Tenant.objects.filter(pk=tenant_id).first() if str(tenant_id).isdigit() else None
    )
    amount = _decimal(raw.get("amount"))
    withholding = _decimal(raw.get("withholding_amount")) if _has_withholding(raw) else Decimal("0")
    settlement = amount + withholding
    if tenant is None or settlement <= 0:
        return None, None, settlement
    rows, credit = suggest_allocations(tenant, settlement)
    return tenant, rows, credit


def _manual_allocations(request):
    found = False
    allocations = {}
    for key, value in request.POST.items():
        if not key.startswith("allocation_"):
            continue
        found = True
        try:
            invoice_id = int(key.split("_", 1)[1])
        except (IndexError, ValueError):
            continue
        if str(value).strip():
            allocations[invoice_id] = value
    return allocations if found else None


@role_required
def payment_new(request):
    initial = {
        "date_received": timezone.localdate(),
        "method": Payment.METHOD_BANK,
    }
    invoice_id = request.GET.get("invoice")
    tenant_id = request.GET.get("tenant")
    if invoice_id and str(invoice_id).isdigit():
        invoice = Invoice.objects.filter(pk=invoice_id).select_related("tenant").first()
        if invoice:
            initial["tenant"] = invoice.tenant
            initial["amount"] = invoice.balance
    elif tenant_id and str(tenant_id).isdigit():
        tenant = Tenant.objects.filter(pk=tenant_id).first()
        if tenant:
            initial["tenant"] = tenant

    form = PaymentForm(request.POST or None, initial=initial)
    error_message = None

    if request.method == "POST" and form.is_valid():
        manual = _manual_allocations(request)
        try:
            payment = record_payment(
                tenant=form.cleaned_data["tenant"],
                date_received=form.cleaned_data["date_received"],
                method=form.cleaned_data["method"],
                amount=form.cleaned_data["amount"] or Decimal("0.00"),
                withholding_amount=form.cleaned_data["withholding_amount"] or Decimal("0.00"),
                reference=form.cleaned_data["reference"],
                cheque_number=form.cleaned_data["cheque_number"],
                cheque_bank=form.cleaned_data["cheque_bank"],
                withholding_cert_no=form.cleaned_data["withholding_cert_no"],
                notes=form.cleaned_data["notes"],
                manual_allocations=manual,
                user=request.user,
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f"Payment {payment.receipt_number} recorded.")
            return redirect("payment_detail", pk=payment.pk)

    raw = request.POST if request.method == "POST" else {
        "tenant": initial.get("tenant").pk if initial.get("tenant") else "",
        "amount": initial.get("amount", ""),
        "has_withholding": "",
        "withholding_amount": "",
    }
    preview_tenant, preview_rows, preview_credit = _preview_values(raw)
    if preview_tenant is None:
        preview_rows = []
        preview_credit = Decimal("0")
    preview_summary = (
        tenant_account_summary(preview_tenant) if preview_tenant is not None else None
    )

    return render(
        request,
        "payments/payment_form.html",
        {
            "form": form,
            "preview_tenant": preview_tenant,
            "preview_rows": preview_rows or [],
            "preview_credit": preview_credit,
            "preview_summary": preview_summary,
            "preview_error": error_message,
        },
    )


@role_required
def allocation_preview(request):
    tenant_id = request.GET.get("tenant")
    tenant = (
        Tenant.objects.filter(pk=tenant_id).first() if str(tenant_id).isdigit() else None
    )
    if tenant is None:
        return JsonResponse({"error": "Unknown tenant."}, status=400)
    summary = tenant_account_summary(tenant)
    summary_json = {
        "units": summary["units"],
        "monthly_rent": f"{summary['monthly_rent']:.2f}",
        "outstanding": f"{summary['outstanding']:.2f}",
        "open_invoices": summary["open_invoices"],
    }
    amount = _decimal(request.GET.get("amount"))
    withholding = (
        _decimal(request.GET.get("withholding_amount"))
        if _has_withholding(request.GET)
        else Decimal("0")
    )
    settlement = amount + withholding
    if settlement <= 0:
        return JsonResponse(
            {
                "settlement": "0.00",
                "credit": "0.00",
                "allocations": [],
                "summary": summary_json,
            }
        )
    rows, credit = suggest_allocations(tenant, settlement)
    return JsonResponse(
        {
            "settlement": f"{settlement:.2f}",
            "credit": f"{credit:.2f}",
            "summary": summary_json,
            "allocations": [
                {
                    "invoice_id": row["invoice"].pk,
                    "invoice_number": row["invoice"].invoice_number,
                    "due_date": row["invoice"].due_date.isoformat(),
                    "balance": f"{row['invoice'].balance:.2f}",
                    "amount": f"{row['amount']:.2f}",
                }
                for row in rows
            ],
        }
    )


@role_required
def payments(request):
    queryset = Payment.objects.select_related("tenant")
    query = request.GET.get("q", "").strip()
    method = request.GET.get("method", "").strip()
    status = request.GET.get("status", "").strip()
    if query:
        queryset = queryset.filter(
            models_q_payment(query)
        )
    if method in dict(Payment.METHOD_CHOICES):
        queryset = queryset.filter(method=method)
    if status in dict(Payment.STATUS_CHOICES):
        queryset = queryset.filter(status=status)
    payment_rows = list(queryset)
    return render(
        request,
        "payments/payments.html",
        {
            "payments": payment_rows,
            "query": query,
            "selected_method": method,
            "selected_status": status,
            "methods": Payment.METHOD_CHOICES,
            "statuses": Payment.STATUS_CHOICES,
            "counts": {
                "total": len(payment_rows),
                "settled": sum(
                    (
                        payment.settlement_amount
                        for payment in payment_rows
                        if payment.status == Payment.STATUS_POSTED
                    ),
                    Decimal("0.00"),
                ),
            },
        },
    )


def models_q_payment(query):
    from django.db.models import Q

    return (
        Q(receipt_number__icontains=query)
        | Q(tenant__business_name__icontains=query)
        | Q(reference__icontains=query)
    )


@role_required
def payment_detail(request, pk):
    payment = get_object_or_404(
        Payment.objects.select_related("tenant"), pk=pk
    )
    return render(
        request,
        "payments/payment_detail.html",
        {
            "payment": payment,
            "allocations": payment.allocations.select_related("invoice"),
            "credit_entries": payment.credit_entries.select_related("invoice"),
        },
    )


@role_required
def payment_pdf(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    pdf = build_receipt_pdf(payment)
    response = HttpResponse(pdf.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{payment.receipt_number}.pdf"'
    return response


@role_required
def payment_thermal(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    data = build_thermal_receipt(payment)
    response = HttpResponse(data, content_type="application/octet-stream")
    response["Content-Disposition"] = (
        f'attachment; filename="{payment.receipt_number}.escpos"'
    )
    return response


@require_POST
@role_required
def payment_void(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    reason = request.POST.get("reason", "").strip()
    void_payment(payment, reason=reason, user=request.user)
    messages.success(request, f"Payment {payment.receipt_number} voided.")
    return redirect("payment_detail", pk=payment.pk)


@require_POST
@role_required
def cheque_banked(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    try:
        mark_cheque_banked(payment, user=request.user)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, "Cheque marked as banked.")
    return redirect("payment_detail", pk=payment.pk)


@require_POST
@role_required
def cheque_bounced(request, pk):
    payment = get_object_or_404(Payment, pk=pk)
    try:
        mark_cheque_bounced(
            payment,
            user=request.user,
            reason=request.POST.get("reason", "Cheque bounced").strip(),
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, "Cheque bounced; allocations reversed.")
    return redirect("payment_detail", pk=payment.pk)


@role_required
def statement_imports(request):
    form = StatementImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            import_run = create_import(
                form.cleaned_data["source"],
                form.cleaned_data["file"],
                user=request.user,
            )
        except StatementImportError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"Imported {import_run.rows.count()} statement rows.")
            return redirect("statement_import_detail", pk=import_run.pk)
    return render(
        request,
        "payments/statements.html",
        {"form": form, "imports": StatementImport.objects.all()},
    )


@role_required
def statement_import_detail(request, pk):
    import_run = get_object_or_404(StatementImport, pk=pk)
    rows = import_run.rows.select_related(
        "suggested_tenant", "suggested_invoice", "payment"
    )
    return render(
        request,
        "payments/statement_import.html",
        {
            "import_run": import_run,
            "rows": rows,
            "tenants": Tenant.objects.order_by("business_name"),
            "counts": {
                "total": rows.count(),
                "confirmed": rows.filter(match_status=StatementRow.MATCH_CONFIRMED).count(),
                "ignored": rows.filter(match_status=StatementRow.MATCH_IGNORED).count(),
                "open": rows.filter(
                    match_status__in=[
                        StatementRow.MATCH_UNMATCHED,
                        StatementRow.MATCH_SUGGESTED,
                    ]
                ).count(),
            },
        },
    )


@require_POST
@role_required
def statement_row_confirm(request, pk):
    row = get_object_or_404(StatementRow, pk=pk)
    tenant = row.suggested_tenant
    tenant_id = request.POST.get("tenant", "").strip()
    if tenant_id:
        tenant = Tenant.objects.filter(pk=tenant_id).first()
    try:
        payment = confirm_row(row, tenant=tenant, user=request.user)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, f"Payment {payment.receipt_number} recorded.")
    return redirect("statement_import_detail", pk=row.import_run_id)


@require_POST
@role_required
def statement_row_ignore(request, pk):
    row = get_object_or_404(StatementRow, pk=pk)
    try:
        ignore_row(row)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, "Statement row ignored.")
    return redirect("statement_import_detail", pk=row.import_run_id)
