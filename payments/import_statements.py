"""CSV statement parsing, suggested matching and confirmation."""

import csv
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import StringIO

from django.core.exceptions import ValidationError
from django.db import transaction

from billing.models import Invoice
from payments.models import Payment, StatementImport, StatementRow
from payments.services import record_payment
from property.models import Lease, Tenant, TenantContact, Unit


class StatementImportError(Exception):
    pass


DATE_ALIASES = {
    "date",
    "tx date",
    "transaction date",
    "completion time",
    "transaction time",
    "value date",
}
AMOUNT_ALIASES = {"paid in", "credit", "amount", "deposit", "money in", "credit amount"}
DEBIT_ALIASES = {"withdrawn", "debit", "money out", "debit amount"}
REFERENCE_ALIASES = {
    "receipt no",
    "receipt no.",
    "receipt",
    "reference",
    "ref",
    "transaction code",
    "transaction id",
    "code",
}
DESCRIPTION_ALIASES = {"details", "description", "narration", "narrative", "particulars"}
PAYER_ALIASES = {"payer", "payer name", "name"}
PHONE_ALIASES = {"phone", "phone number", "msisdn", "payer phone", "mobile"}
STATUS_ALIASES = {"transaction status", "status", "state"}


def _normalise(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("latin-1", errors="replace")


def _parse_date(value):
    text = str(value or "").strip()
    if not text:
        return None
    for pattern in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
    ):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def _parse_amount(value):
    text = str(value or "").strip().replace(",", "")
    text = re.sub(r"^(kes|ksh|usd|kshs)\s*", "", text, flags=re.IGNORECASE)
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _column_index(headers, aliases):
    for index, header in enumerate(headers):
        if header in aliases:
            return index
    return None


def parse_csv(content: bytes, source: str):
    text = _decode(content)
    reader = csv.reader(StringIO(text))
    raw_rows = [row for row in reader if any(str(cell).strip() for cell in row)]
    if not raw_rows:
        raise StatementImportError("The CSV file is empty.")

    header_index = None
    headers = []
    for index, row in enumerate(raw_rows[:12]):
        candidate = [_normalise(cell) for cell in row]
        if _column_index(candidate, DATE_ALIASES) is not None and (
            _column_index(candidate, AMOUNT_ALIASES) is not None
            or _column_index(candidate, DEBIT_ALIASES) is not None
        ):
            header_index = index
            headers = candidate
            break
    if header_index is None:
        raise StatementImportError(
            "Could not find date and amount columns in the header row."
        )

    date_idx = _column_index(headers, DATE_ALIASES)
    amount_idx = _column_index(headers, AMOUNT_ALIASES)
    debit_idx = _column_index(headers, DEBIT_ALIASES)
    reference_idx = _column_index(headers, REFERENCE_ALIASES)
    description_idx = _column_index(headers, DESCRIPTION_ALIASES)
    payer_idx = _column_index(headers, PAYER_ALIASES)
    phone_idx = _column_index(headers, PHONE_ALIASES)
    status_idx = _column_index(headers, STATUS_ALIASES)

    def cell(row, index):
        if index is None or index >= len(row):
            return ""
        return str(row[index]).strip()

    transactions = []
    for row in raw_rows[header_index + 1 :]:
        if status_idx is not None:
            status = _normalise(cell(row, status_idx))
            if status and not any(
                word in status for word in ("completed", "success", "paid", "ok")
            ):
                continue

        credit = _parse_amount(cell(row, amount_idx)) if amount_idx is not None else None
        debit = _parse_amount(cell(row, debit_idx)) if debit_idx is not None else None
        amount = credit
        if amount is None or amount == 0:
            if debit is not None and debit > 0 and (credit is None or credit == 0):
                continue
            amount = debit
        if amount is None or amount <= 0:
            continue

        tx_date = _parse_date(cell(row, date_idx))
        if tx_date is None:
            continue

        reference = cell(row, reference_idx)
        description = cell(row, description_idx)
        payer_name = cell(row, payer_idx)
        phone = cell(row, phone_idx)
        if not phone:
            match = re.search(r"(\+?254\d{9}|0\d{9})", description)
            if match:
                phone = match.group(1)
        if not payer_name and description:
            payer_name = description.split("-")[0].strip()[:150]

        transactions.append(
            {
                "tx_date": tx_date,
                "amount": amount,
                "reference": reference[:150],
                "payer_name": payer_name[:150],
                "phone": phone[:30],
                "description": description,
            }
        )

    if not transactions:
        raise StatementImportError("No valid credit rows were found in the CSV.")
    return transactions


def suggest_match(transaction):
    haystack = f"{transaction['reference']} {transaction['description']}".upper()

    for invoice in (
        Invoice.objects.filter(status=Invoice.STATUS_ISSUED)
        .select_related("tenant")
        .order_by("-issue_date", "-id")[:1000]
    ):
        if invoice.invoice_number.upper() in haystack:
            return invoice.tenant, invoice

    for tenant in Tenant.objects.all().order_by("business_name"):
        if tenant.business_name.upper() in haystack:
            return tenant, None

    phone_digits = re.sub(r"\D", "", transaction.get("phone") or "")
    if len(phone_digits) >= 9:
        contact = (
            TenantContact.objects.filter(phone__endswith=phone_digits[-9:])
            .select_related("tenant")
            .first()
        )
        if contact:
            return contact.tenant, None

    for token in set(re.findall(r"\b[A-Z]\d{2,4}\b", haystack)):
        unit = Unit.objects.filter(code__iexact=token).first()
        if unit:
            lease = (
                Lease.objects.filter(unit=unit)
                .exclude(status=Lease.STATUS_DRAFT)
                .order_by("-start_date")
                .select_related("tenant")
                .first()
            )
            if lease:
                return lease.tenant, None

    return None, None


def create_import(source, upload, user=None):
    content = upload.read()
    upload.seek(0)
    try:
        transactions = parse_csv(content, source)
    except StatementImportError:
        raise

    with transaction.atomic():
        import_run = StatementImport.objects.create(
            source=source, file=upload, uploaded_by=user
        )
        for tx in transactions:
            tenant, invoice = suggest_match(tx)
            StatementRow.objects.create(
                import_run=import_run,
                tx_date=tx["tx_date"],
                amount=tx["amount"],
                reference=tx["reference"],
                payer_name=tx["payer_name"],
                phone=tx["phone"],
                suggested_tenant=tenant,
                suggested_invoice=invoice,
                match_status=(
                    StatementRow.MATCH_SUGGESTED
                    if tenant
                    else StatementRow.MATCH_UNMATCHED
                ),
            )
    return import_run


def complete_if_done(import_run):
    pending = import_run.rows.filter(
        match_status__in=[
            StatementRow.MATCH_UNMATCHED,
            StatementRow.MATCH_SUGGESTED,
        ]
    ).exists()
    if not pending:
        import_run.status = StatementImport.STATUS_COMPLETED
        import_run.save(update_fields=["status", "updated_at"])


def confirm_row(row: StatementRow, tenant=None, user=None):
    if row.match_status in (
        StatementRow.MATCH_CONFIRMED,
        StatementRow.MATCH_IGNORED,
    ):
        raise ValidationError("This statement row has already been resolved.")
    tenant = tenant or row.suggested_tenant
    if tenant is None:
        raise ValidationError("Choose the tenant for this statement row.")
    method = (
        Payment.METHOD_MPESA
        if row.import_run.source == StatementImport.SOURCE_MPESA
        else Payment.METHOD_BANK
    )
    payment = record_payment(
        tenant=tenant,
        date_received=row.tx_date,
        method=method,
        amount=row.amount,
        reference=row.reference,
        notes=f"Statement import #{row.import_run_id}",
        statement_row=row,
        user=user,
    )
    row.refresh_from_db()
    row.match_status = StatementRow.MATCH_CONFIRMED
    row.save(update_fields=["match_status", "updated_at"])
    complete_if_done(row.import_run)
    return payment


def ignore_row(row: StatementRow):
    if row.match_status == StatementRow.MATCH_CONFIRMED:
        raise ValidationError("A confirmed row cannot be ignored.")
    row.match_status = StatementRow.MATCH_IGNORED
    row.save(update_fields=["match_status", "updated_at"])
    complete_if_done(row.import_run)
    return row
