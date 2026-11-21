"""Reporting queries and dashboard numbers, all derived from the ledger."""

from collections import OrderedDict
from datetime import date, timedelta
from decimal import Decimal
from urllib.parse import quote

from django.db.models import Q, Sum
from django.utils import timezone

from billing.models import Invoice, InvoiceLine, with_balances
from billing.services import add_months
from core.models import Settings
from operations.models import Expense, MaintenanceRequest
from payments.models import Payment
from property.models import Lease, Unit

MONEY = Decimal("0.01")
AGE_BUCKETS = ["0-30", "31-60", "61-90", "90+"]


def month_start(value: date) -> date:
    return value.replace(day=1)


def month_end(value: date) -> date:
    return add_months(month_start(value), 1) - timedelta(days=1)


def month_label(value: date) -> str:
    return value.strftime("%b %Y")


def last_months(count=6, today=None):
    today = today or timezone.localdate()
    start = month_start(today)
    months = []
    for offset in range(count - 1, -1, -1):
        first = add_months(start, -offset)
        months.append((first, month_end(first)))
    return months


def money(value) -> Decimal:
    return (value or Decimal("0.00")).quantize(MONEY)


def invoices_in_period(period_start, period_end):
    return Invoice.objects.filter(
        status=Invoice.STATUS_ISSUED,
        period_start__gte=period_start,
        period_start__lte=period_end,
    )


def billed_between(start, end) -> Decimal:
    value = invoices_in_period(start, end).aggregate(total=Sum("total"))["total"]
    return money(value)


def collected_between(start, end) -> Decimal:
    value = sum(
        (
            payment.settlement_amount
            for payment in Payment.objects.filter(
                status=Payment.STATUS_POSTED,
                date_received__gte=start,
                date_received__lte=end,
            )
        ),
        Decimal("0.00"),
    )
    return money(value)


def expenses_between(start, end) -> Decimal:
    value = Expense.objects.filter(
        expense_date__gte=start, expense_date__lte=end
    ).aggregate(total=Sum("amount"))["total"]
    return money(value)


def overdue_invoices(as_of=None):
    as_of = as_of or timezone.localdate()
    invoices = with_balances(
        Invoice.objects.filter(
            status=Invoice.STATUS_ISSUED,
            due_date__lt=as_of,
        )
        .select_related("tenant", "unit")
        .order_by("due_date", "id")
    )
    return [invoice for invoice in invoices if invoice.balance > 0]


def bucket_for(days):
    if days <= 30:
        return "0-30"
    if days <= 60:
        return "31-60"
    if days <= 90:
        return "61-90"
    return "90+"


def arrears_buckets(as_of=None):
    as_of = as_of or timezone.localdate()
    buckets = {label: Decimal("0.00") for label in AGE_BUCKETS}
    for invoice in overdue_invoices(as_of):
        days = (as_of - invoice.due_date).days
        buckets[bucket_for(days)] += invoice.balance
    return {key: money(value) for key, value in buckets.items()}


def arrears_report(as_of=None):
    as_of = as_of or timezone.localdate()
    rows = []
    for invoice in overdue_invoices(as_of):
        days = (as_of - invoice.due_date).days
        rows.append(
            {
                "invoice": invoice,
                "tenant": invoice.tenant,
                "unit": invoice.unit,
                "due_date": invoice.due_date,
                "days": days,
                "bucket": bucket_for(days),
                "total": invoice.total,
                "paid": invoice.amount_paid,
                "balance": invoice.balance,
            }
        )
    return rows, arrears_buckets(as_of)


def monthly_income_expense(start, end):
    rows = []
    cursor = month_start(start)
    while cursor <= end:
        first = max(cursor, start)
        last = min(month_end(cursor), end)
        collected = collected_between(first, last)
        billed = billed_between(first, last)
        expenses = expenses_between(first, last)
        rows.append(
            {
                "month": month_label(first),
                "from": first,
                "to": last,
                "billed": billed,
                "collected": collected,
                "expenses": expenses,
                "net": money(collected - expenses),
            }
        )
        cursor = add_months(cursor, 1)
    return rows


def occupancy_report(building=None, today=None):
    today = today or timezone.localdate()
    units = Unit.objects.filter(is_active=True).select_related("building", "floor")
    if building is not None:
        units = units.filter(building=building)
    units = list(units.order_by("building__name", "floor__sort_order", "code"))
    active_leases = {
        lease.unit_id: lease
        for lease in Lease.objects.filter(
            status=Lease.STATUS_ACTIVE,
            start_date__lte=today,
        )
        .filter(Q(end_date__gte=today) | Q(end_date__isnull=True))
        .select_related("tenant")
    }
    rows = []
    counts = {
        Unit.STATUS_OCCUPIED: 0,
        Unit.STATUS_VACANT: 0,
        Unit.STATUS_RESERVED: 0,
    }
    for unit in units:
        lease = active_leases.get(unit.pk)
        counts[unit.status] = counts.get(unit.status, 0) + 1
        rows.append(
            {
                "unit": unit,
                "status": unit.get_status_display(),
                "tenant": lease.tenant.business_name if lease else "-",
                "lease_end": lease.end_date if lease else None,
                "rent": unit.base_rent,
            }
        )
    total = len(rows)
    occupied = counts.get(Unit.STATUS_OCCUPIED, 0)
    rate = (Decimal(occupied) / Decimal(total) * 100) if total else Decimal("0.00")
    return rows, counts, money(rate)


def tenant_statement(tenant, start, end):
    events = []
    for invoice in tenant.invoices.filter(status=Invoice.STATUS_ISSUED).select_related(
        "unit"
    ):
        events.append(
            {
                "date": invoice.issue_date,
                "order": 1,
                "description": f"Invoice {invoice.invoice_number}",
                "invoice": invoice,
                "charged": invoice.total,
                "paid": Decimal("0.00"),
            }
        )
    for payment in tenant.payments.filter(status=Payment.STATUS_POSTED):
        events.append(
            {
                "date": payment.date_received,
                "order": 2,
                "description": f"Receipt {payment.receipt_number}",
                "payment": payment,
                "charged": Decimal("0.00"),
                "paid": payment.settlement_amount,
            }
        )
    events.sort(key=lambda event: (event["date"], event["order"], event.get("invoice") and event["invoice"].pk or 0))

    opening = Decimal("0.00")
    in_range = []
    for event in events:
        if event["date"] < start:
            opening += event["charged"] - event["paid"]
        elif event["date"] <= end:
            in_range.append(event)

    running = opening
    for event in in_range:
        running += event["charged"] - event["paid"]
        event["balance"] = running

    return {
        "opening": money(opening),
        "rows": in_range,
        "closing": money(running),
    }


def tax_summary(start, end):
    rows = []
    cursor = month_start(start)
    while cursor <= end:
        first = max(cursor, start)
        last = min(month_end(cursor), end)
        invoices = Invoice.objects.filter(
            status=Invoice.STATUS_ISSUED,
            issue_date__gte=first,
            issue_date__lte=last,
        )
        invoice_ids = list(invoices.values_list("pk", flat=True))
        rent_billed = InvoiceLine.objects.filter(
            invoice_id__in=invoice_ids,
            kind=InvoiceLine.KIND_RENT,
        ).aggregate(total=Sum("amount"))["total"]
        vat_charged = invoices.aggregate(total=Sum("vat_amount"))["total"]
        withholding = Payment.objects.filter(
            status=Payment.STATUS_POSTED,
            date_received__gte=first,
            date_received__lte=last,
        ).aggregate(total=Sum("withholding_amount"))["total"]
        rows.append(
            {
                "month": month_label(first),
                "invoices": len(invoice_ids),
                "rent_billed": money(rent_billed),
                "vat_charged": money(vat_charged),
                "withholding": money(withholding),
            }
        )
        cursor = add_months(cursor, 1)
    return rows


def normalize_phone(phone: str) -> str:
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if not digits:
        return ""
    if digits.startswith("254"):
        return digits
    if digits.startswith("0"):
        return "254" + digits[1:]
    if len(digits) == 9 and digits.startswith("7"):
        return "254" + digits
    return digits


def reminder_message(tenant, invoice, balance, settings_obj=None):
    settings_obj = settings_obj or Settings.load()
    template = settings_obj.reminder_template or ""
    try:
        return template.format(
            tenant=tenant.business_name,
            invoice=invoice.invoice_number,
            unit=invoice.unit.code,
            balance=f"{settings_obj.currency} {balance:,.2f}",
        )
    except (KeyError, ValueError, IndexError):
        return template


def overdue_reminders(as_of=None):
    settings_obj = Settings.load()
    as_of = as_of or timezone.localdate()
    grouped = OrderedDict()
    for invoice in overdue_invoices(as_of):
        grouped.setdefault(invoice.tenant_id, []).append(invoice)

    rows = []
    for tenant_id, invoices in grouped.items():
        tenant = invoices[0].tenant
        oldest = invoices[0]
        balance = sum((invoice.balance for invoice in invoices), Decimal("0.00"))
        contact = tenant.primary_contact
        phone = contact.phone if contact else ""
        normalized = normalize_phone(phone)
        message = reminder_message(tenant, oldest, balance, settings_obj)
        rows.append(
            {
                "tenant": tenant,
                "unit": oldest.unit,
                "invoice": oldest,
                "invoices": invoices,
                "balance": money(balance),
                "days": (as_of - oldest.due_date).days,
                "phone": phone,
                "whatsapp_url": (
                    f"https://wa.me/{normalized}?text={quote(message)}" if normalized else ""
                ),
                "call_url": f"tel:{phone}" if phone else "",
                "message": message,
            }
        )
    return rows


def dashboard_summary(today=None):
    today = today or timezone.localdate()
    current_start = month_start(today)
    current_end = month_end(today)
    units = Unit.objects.filter(is_active=True)
    total_units = units.count()
    occupied_units = units.filter(status=Unit.STATUS_OCCUPIED).count()
    overdue = overdue_invoices(today)
    arrears = sum((invoice.balance for invoice in overdue), Decimal("0.00"))

    settings_obj = Settings.load()
    renewal_days = settings_obj.renewal_alert_days
    leases_ending = Lease.objects.filter(
        status=Lease.STATUS_ACTIVE,
        end_date__gte=today,
        end_date__lte=today + timedelta(days=renewal_days),
    ).count()
    rent_increases = Lease.objects.filter(
        status=Lease.STATUS_ACTIVE,
        next_escalation_date__year=today.year,
        next_escalation_date__month=today.month,
    ).count()
    open_maintenance = MaintenanceRequest.objects.exclude(
        status=MaintenanceRequest.STATUS_DONE
    ).count()
    overdue_tenant_count = len({invoice.tenant_id for invoice in overdue})

    months = []
    for first, last in last_months(6, today):
        months.append(
            {
                "label": month_label(first),
                "income": float(collected_between(first, last)),
                "expenses": float(expenses_between(first, last)),
            }
        )

    buckets = arrears_buckets(today)

    return {
        "rent_due": billed_between(current_start, current_end),
        "collected": collected_between(current_start, current_end),
        "arrears": money(arrears),
        "occupied": occupied_units,
        "total_units": total_units,
        "occupied_label": f"{occupied_units} / {total_units}",
        "overdue_tenants": overdue_tenant_count,
        "leases_ending": leases_ending,
        "rent_increases": rent_increases,
        "open_maintenance": open_maintenance,
        "months": months,
        "buckets": buckets,
        "renewal_days": renewal_days,
    }
