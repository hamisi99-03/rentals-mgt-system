from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from payments.import_statements import confirm_row, create_import, parse_csv
from payments.models import Payment, StatementImport, StatementRow
from property.models import TenantContact

pytestmark = pytest.mark.django_db

MPESA_CSV = """Receipt No.,Completion Time,Details,Transaction Status,Paid In,Withdrawn,Balance
QK81ABC,2026-11-03 10:00:00,INV-A01-0001 MAMA MBOGA 254700000001,Completed,1000.00,,5000.00
QK82DEF,2026-11-04 11:00:00,UNKNOWN PAYER,Completed,500.00,,4500.00
QK83GHI,2026-11-04 12:00:00,WITHDRAWAL,Completed,,200.00,4300.00
QK84JKL,2026-11-04 13:00:00,FAILED PAYMENT,Failed,300.00,,4000.00
"""

BANK_CSV = """Date,Description,Amount,Reference
05/11/2026,Customer deposit,750.00,BANK123
06/11/2026,Salon Bella payment,1200.00,BANK124
"""


def test_parse_mpesa_rows_and_skip_withdrawals():
    transactions = parse_csv(MPESA_CSV.encode("utf-8"), "mpesa")
    assert len(transactions) == 2
    assert transactions[0]["amount"] == Decimal("1000.00")
    assert transactions[0]["reference"] == "QK81ABC"
    assert transactions[0]["tx_date"] == date(2026, 11, 3)


def test_parse_bank_rows():
    transactions = parse_csv(BANK_CSV.encode("utf-8"), "bank")
    assert len(transactions) == 2
    assert transactions[0]["tx_date"] == date(2026, 11, 5)
    assert transactions[1]["amount"] == Decimal("1200.00")


def test_statement_import_is_bank_only():
    from payments.forms import StatementImportForm

    form = StatementImportForm()
    assert list(dict(form.fields["source"].choices)) == ["bank"]


def test_upload_never_posts_payments(logged_in, invoice):
    response = logged_in.post(
        reverse("statement_imports"),
        {
            "source": "bank",
            "file": SimpleUploadedFile("mpesa.csv", MPESA_CSV.encode(), content_type="text/csv"),
        },
    )
    assert response.status_code == 302
    import_run = StatementImport.objects.get()
    assert import_run.rows.count() == 2
    assert Payment.objects.count() == 0

    rows = list(import_run.rows.all())
    suggested = next(row for row in rows if row.match_status == StatementRow.MATCH_SUGGESTED)
    unmatched = next(row for row in rows if row.match_status == StatementRow.MATCH_UNMATCHED)
    assert suggested.suggested_tenant == invoice.tenant
    assert suggested.suggested_invoice == invoice
    assert unmatched.suggested_tenant is None


def test_confirm_suggested_row_records_payment(logged_in, invoice):
    response = logged_in.post(
        reverse("statement_imports"),
        {
            "source": "bank",
            "file": SimpleUploadedFile("mpesa.csv", MPESA_CSV.encode(), content_type="text/csv"),
        },
    )
    import_run = StatementImport.objects.get()
    row = import_run.rows.get(match_status=StatementRow.MATCH_SUGGESTED)

    response = logged_in.post(reverse("statement_row_confirm", kwargs={"pk": row.pk}))
    assert response.status_code == 302
    row.refresh_from_db()
    import_run.refresh_from_db()
    assert row.match_status == StatementRow.MATCH_CONFIRMED
    assert row.payment is not None
    assert invoice.balance == Decimal("0.00")
    assert Payment.objects.count() == 1
    assert import_run.status == StatementImport.STATUS_PENDING

    unmatched = import_run.rows.get(match_status=StatementRow.MATCH_UNMATCHED)
    logged_in.post(reverse("statement_row_ignore", kwargs={"pk": unmatched.pk}))
    import_run.refresh_from_db()
    assert import_run.status == StatementImport.STATUS_COMPLETED


def test_unmatched_row_cannot_confirm_without_tenant(logged_in, invoice):
    logged_in.post(
        reverse("statement_imports"),
        {
            "source": "bank",
            "file": SimpleUploadedFile("mpesa.csv", MPESA_CSV.encode(), content_type="text/csv"),
        },
    )
    row = StatementImport.objects.get().rows.get(match_status=StatementRow.MATCH_UNMATCHED)
    response = logged_in.post(reverse("statement_row_confirm", kwargs={"pk": row.pk}))
    assert response.status_code == 302
    assert Payment.objects.count() == 0
    row.refresh_from_db()
    assert row.match_status == StatementRow.MATCH_UNMATCHED


def test_unmatched_row_can_be_picked_and_confirmed(logged_in, invoice, tenant):
    logged_in.post(
        reverse("statement_imports"),
        {
            "source": "bank",
            "file": SimpleUploadedFile("mpesa.csv", MPESA_CSV.encode(), content_type="text/csv"),
        },
    )
    row = StatementImport.objects.get().rows.get(match_status=StatementRow.MATCH_UNMATCHED)
    response = logged_in.post(
        reverse("statement_row_confirm", kwargs={"pk": row.pk}),
        {"tenant": tenant.pk},
    )
    assert response.status_code == 302
    row.refresh_from_db()
    assert row.match_status == StatementRow.MATCH_CONFIRMED
    assert row.payment is not None


def test_ignore_row(logged_in):
    logged_in.post(
        reverse("statement_imports"),
        {
            "source": "bank",
            "file": SimpleUploadedFile("bank.csv", BANK_CSV.encode(), content_type="text/csv"),
        },
    )
    import_run = StatementImport.objects.get()
    row = import_run.rows.first()
    logged_in.post(reverse("statement_row_ignore", kwargs={"pk": row.pk}))
    row.refresh_from_db()
    assert row.match_status == StatementRow.MATCH_IGNORED


def test_phone_match_suggestion(invoice):
    TenantContact.objects.create(
        tenant=invoice.tenant, name="Asha", phone="+254700000001"
    )
    csv_text = """Receipt No.,Completion Time,Details,Transaction Status,Paid In,Withdrawn,Balance
QK90XYZ,2026-11-07 09:00:00,PAYMENT 254700000001,Completed,900.00,,1000.00
"""
    import_run = create_import(
        "mpesa",
        SimpleUploadedFile("phone.csv", csv_text.encode(), content_type="text/csv"),
    )
    row = import_run.rows.get()
    assert row.suggested_tenant == invoice.tenant


def test_bank_import_page_and_detail(logged_in, invoice):
    response = logged_in.post(
        reverse("statement_imports"),
        {
            "source": "bank",
            "file": SimpleUploadedFile("bank.csv", BANK_CSV.encode(), content_type="text/csv"),
        },
    )
    assert response.status_code == 302
    import_run = StatementImport.objects.get()
    response = logged_in.get(reverse("statement_import_detail", kwargs={"pk": import_run.pk}))
    assert response.status_code == 200
    assert b"Statement" in response.content
    response = logged_in.get(reverse("statement_imports"))
    assert response.status_code == 200


def test_confirm_row_service_requires_tenant(invoice):
    import_run = create_import(
        "mpesa",
        SimpleUploadedFile("mpesa.csv", MPESA_CSV.encode(), content_type="text/csv"),
    )
    row = import_run.rows.get(match_status=StatementRow.MATCH_UNMATCHED)
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        confirm_row(row)
