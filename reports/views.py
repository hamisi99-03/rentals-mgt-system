"""Reports hub, report screens, exports and overdue reminders."""

from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from billing.services import add_months
from core.permissions import role_required
from reports.export import build_table_pdf, build_table_xlsx
from reports.forms import ArrearsForm, DateRangeForm, OccupancyForm, TenantStatementForm
from reports.services import (
    arrears_report,
    monthly_income_expense,
    occupancy_report,
    overdue_reminders,
    tax_summary,
    tenant_statement,
)
from property.models import Building
from property.services import refresh_lease_statuses

MONEY = Decimal("0.01")


def _range_defaults():
    today = timezone.localdate()
    return {
        "start_date": today.replace(month=1, day=1),
        "end_date": today,
    }


def _monthly_defaults():
    today = timezone.localdate()
    return {
        "start_date": add_months(today.replace(day=1), -5),
        "end_date": today,
    }


def _export_response(kind, title, headers, rows, totals=None, filename="report"):
    if kind == "xlsx":
        stream = build_table_xlsx(title, headers, rows, totals=totals)
        response = HttpResponse(
            stream.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
        return response
    stream = build_table_pdf(title, headers, rows, totals=totals)
    response = HttpResponse(stream.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}.pdf"'
    return response


@role_required
def reports_home(request):
    return render(request, "reports/index.html")


@role_required
def arrears(request):
    today = timezone.localdate()
    form = ArrearsForm({"as_of": request.GET.get("as_of") or today.isoformat()})
    rows = []
    buckets = {}
    if form.is_valid():
        rows, buckets = arrears_report(form.cleaned_data["as_of"])
    else:
        messages.error(request, "Enter a valid date.")
        form = ArrearsForm({"as_of": today.isoformat()})

    export = request.GET.get("export")
    if export in ("xlsx", "pdf") and form.is_valid():
        headers = ["Invoice", "Tenant", "Unit", "Due", "Days", "Bucket", "Total", "Paid", "Balance"]
        data = [
            [
                row["invoice"].invoice_number,
                row["tenant"].business_name,
                row["unit"].code,
                row["due_date"],
                row["days"],
                row["bucket"],
                row["total"],
                row["paid"],
                row["balance"],
            ]
            for row in rows
        ]
        totals = [
            "",
            "",
            "",
            "",
            "",
            "Total",
            sum((row["total"] for row in rows), Decimal("0.00")),
            sum((row["paid"] for row in rows), Decimal("0.00")),
            sum((row["balance"] for row in rows), Decimal("0.00")),
        ]
        return _export_response(
            export, "Arrears report", headers, data, totals, "arrears"
        )

    return render(
        request,
        "reports/arrears.html",
        {"form": form, "rows": rows, "buckets": buckets},
    )


@role_required
def monthly(request):
    defaults = _monthly_defaults()
    data = {
        "start_date": request.GET.get("start_date") or defaults["start_date"].isoformat(),
        "end_date": request.GET.get("end_date") or defaults["end_date"].isoformat(),
    }
    form = DateRangeForm(data)
    rows = []
    if form.is_valid():
        rows = monthly_income_expense(
            form.cleaned_data["start_date"], form.cleaned_data["end_date"]
        )
    else:
        messages.error(request, "Choose a valid date range.")

    export = request.GET.get("export")
    if export in ("xlsx", "pdf") and form.is_valid():
        headers = ["Month", "Billed", "Collected", "Expenses", "Net"]
        data_rows = [
            [row["month"], row["billed"], row["collected"], row["expenses"], row["net"]]
            for row in rows
        ]
        totals = [
            "Total",
            sum((row["billed"] for row in rows), Decimal("0.00")),
            sum((row["collected"] for row in rows), Decimal("0.00")),
            sum((row["expenses"] for row in rows), Decimal("0.00")),
            sum((row["net"] for row in rows), Decimal("0.00")),
        ]
        return _export_response(
            export, "Monthly income and expenses", headers, data_rows, totals, "monthly-income-expense"
        )

    return render(request, "reports/monthly.html", {"form": form, "rows": rows})


@role_required
def occupancy(request):
    refresh_lease_statuses()
    form = OccupancyForm({"building": request.GET.get("building") or ""})
    rows = []
    counts = {}
    rate = Decimal("0.00")
    if form.is_valid():
        rows, counts, rate = occupancy_report(
            form.cleaned_data.get("building")
        )
    else:
        messages.error(request, "Choose a valid building.")

    export = request.GET.get("export")
    if export in ("xlsx", "pdf") and form.is_valid():
        headers = ["Unit", "Building", "Floor", "Status", "Tenant", "Lease end", "Base rent"]
        data_rows = [
            [
                row["unit"].code,
                row["unit"].building.name,
                row["unit"].floor.name,
                row["status"],
                row["tenant"],
                row["lease_end"],
                row["rent"],
            ]
            for row in rows
        ]
        return _export_response(
            export, "Occupancy and vacancy", headers, data_rows, None, "occupancy"
        )

    return render(
        request,
        "reports/occupancy.html",
        {
            "form": form,
            "rows": rows,
            "counts": counts,
            "rate": rate,
            "buildings": Building.objects.all(),
        },
    )


@role_required
def statement(request):
    defaults = _range_defaults()
    tenant_id = request.GET.get("tenant")
    statement_data = None
    form = TenantStatementForm(
        {
            "tenant": tenant_id,
            "start_date": request.GET.get("start_date") or defaults["start_date"].isoformat(),
            "end_date": request.GET.get("end_date") or defaults["end_date"].isoformat(),
        }
        if tenant_id
        else None,
        initial={
            **defaults,
        },
    )

    if tenant_id:
        if form.is_valid():
            statement_data = tenant_statement(
                form.cleaned_data["tenant"],
                form.cleaned_data["start_date"],
                form.cleaned_data["end_date"],
            )
        else:
            messages.error(request, "Choose a valid tenant and date range.")

    export = request.GET.get("export")
    if export in ("xlsx", "pdf") and statement_data is not None:
        headers = ["Date", "Description", "Charged", "Paid", "Balance"]
        data_rows = [
            ["", "Opening balance", "", "", statement_data["opening"]]
        ]
        for row in statement_data["rows"]:
            data_rows.append(
                [
                    row["date"],
                    row["description"],
                    row["charged"],
                    row["paid"],
                    row["balance"],
                ]
            )
        data_rows.append(["", "Closing balance", "", "", statement_data["closing"]])
        return _export_response(
            export, "Tenant statement", headers, data_rows, None, "tenant-statement"
        )

    return render(
        request,
        "reports/statement.html",
        {"form": form, "statement": statement_data},
    )


@role_required
def tax(request):
    defaults = _range_defaults()
    data = {
        "start_date": request.GET.get("start_date") or defaults["start_date"].isoformat(),
        "end_date": request.GET.get("end_date") or defaults["end_date"].isoformat(),
    }
    form = DateRangeForm(data)
    rows = []
    if form.is_valid():
        rows = tax_summary(form.cleaned_data["start_date"], form.cleaned_data["end_date"])
    else:
        messages.error(request, "Choose a valid date range.")

    export = request.GET.get("export")
    if export in ("xlsx", "pdf") and form.is_valid():
        headers = ["Month", "Invoices", "Rent billed", "VAT charged", "Withholding deducted"]
        data_rows = [
            [
                row["month"],
                row["invoices"],
                row["rent_billed"],
                row["vat_charged"],
                row["withholding"],
            ]
            for row in rows
        ]
        totals = [
            "Total",
            sum((row["invoices"] for row in rows), 0),
            sum((row["rent_billed"] for row in rows), Decimal("0.00")),
            sum((row["vat_charged"] for row in rows), Decimal("0.00")),
            sum((row["withholding"] for row in rows), Decimal("0.00")),
        ]
        return _export_response(
            export, "Tax summary", headers, data_rows, totals, "tax-summary"
        )

    return render(
        request,
        "reports/tax.html",
        {"form": form, "rows": rows},
    )


@role_required
def reminders(request):
    rows = overdue_reminders()
    export = request.GET.get("export")
    if export in ("xlsx", "pdf"):
        headers = ["Tenant", "Unit", "Invoice", "Days overdue", "Balance", "Phone"]
        data_rows = [
            [
                row["tenant"].business_name,
                row["unit"].code,
                row["invoice"].invoice_number,
                row["days"],
                row["balance"],
                row["phone"],
            ]
            for row in rows
        ]
        totals = [
            "",
            "",
            "",
            "",
            sum((row["balance"] for row in rows), Decimal("0.00")),
            "",
        ]
        return _export_response(
            export, "Overdue reminders", headers, data_rows, totals, "overdue-reminders"
        )

    return render(
        request,
        "reports/reminders.html",
        {"rows": rows, "today": timezone.localdate()},
    )
