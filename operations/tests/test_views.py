from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from billing.services import add_months, generate_invoice
from operations.forms import MoveOutItemFormSet
from operations.models import (
    Deposit,
    Expense,
    ExpenseCategory,
    MaintenanceRequest,
    MoveOut,
    MoveOutItem,
    Prospect,
)
from payments.services import record_payment
from property.models import Document, Lease, Tenant, Unit

pytestmark = pytest.mark.django_db


def test_operations_pages_require_login(client, lease):
    for url in (
        reverse("prospects"),
        reverse("move_outs"),
        reverse("maintenance"),
        reverse("expenses"),
        reverse("expense_categories"),
        reverse("lease_deposits", kwargs={"lease_pk": lease.pk}),
    ):
        response = client.get(url)
        assert response.status_code == 302
        assert "/accounts/login/" in response["Location"]


def test_record_deposit_view(logged_in, lease):
    response = logged_in.get(reverse("lease_deposits", kwargs={"lease_pk": lease.pk}))
    assert response.status_code == 200

    response = logged_in.post(
        reverse("lease_deposits", kwargs={"lease_pk": lease.pk}),
        {"amount_received": "2000.00", "received_date": timezone.localdate().isoformat()},
    )
    assert response.status_code == 302
    deposit = Deposit.objects.get(lease=lease)
    assert deposit.amount_received == Decimal("2000.00")
    assert deposit.status == Deposit.STATUS_HELD


def test_move_out_create_detail_checklist_and_settle(logged_in, lease, invoice, unit):
    from operations.services import record_deposit

    record_deposit(lease, "2000.00", timezone.localdate())
    move_out_date = timezone.localdate() + timedelta(days=30)

    response = logged_in.post(
        reverse("move_out_create", kwargs={"lease_pk": lease.pk}),
        {
            "notice_date": timezone.localdate().isoformat(),
            "move_out_date": move_out_date.isoformat(),
            "settlement_notes": "Keys returned",
        },
    )
    assert response.status_code == 302
    move_out = MoveOut.objects.get(lease=lease)
    assert move_out.items.count() == 5
    assert move_out.refund_amount == Decimal("1000.00")

    response = logged_in.get(reverse("move_out_detail", kwargs={"pk": move_out.pk}))
    assert response.status_code == 200

    formset = MoveOutItemFormSet(instance=move_out)
    prefix = formset.prefix
    data = {
        f"{prefix}-TOTAL_FORMS": "5",
        f"{prefix}-INITIAL_FORMS": "5",
        f"{prefix}-MIN_NUM_FORMS": "0",
        f"{prefix}-MAX_NUM_FORMS": "1000",
    }
    for index, item in enumerate(move_out.items.all()):
        data[f"{prefix}-{index}-id"] = item.pk
        data[f"{prefix}-{index}-move_out"] = move_out.pk
        data[f"{prefix}-{index}-item"] = item.item
        data[f"{prefix}-{index}-condition"] = (
            "damaged" if item.item == MoveOutItem.ITEM_SHUTTER else "ok"
        )
        data[f"{prefix}-{index}-damage_cost"] = (
            "300.00" if item.item == MoveOutItem.ITEM_SHUTTER else "0.00"
        )
        data[f"{prefix}-{index}-notes"] = ""

    response = logged_in.post(reverse("move_out_detail", kwargs={"pk": move_out.pk}), data)
    assert response.status_code == 302
    move_out.refresh_from_db()
    assert move_out.damages_amount == Decimal("300.00")
    assert move_out.refund_amount == Decimal("700.00")

    response = logged_in.get(reverse("move_out_pdf", kwargs={"pk": move_out.pk}))
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")

    response = logged_in.post(reverse("move_out_settle", kwargs={"pk": move_out.pk}))
    assert response.status_code == 302
    move_out.refresh_from_db()
    lease.refresh_from_db()
    unit.refresh_from_db()
    assert move_out.status == MoveOut.STATUS_SETTLED
    assert lease.status == Lease.STATUS_TERMINATED
    assert unit.status == Unit.STATUS_VACANT


def test_move_out_captures_final_readings(logged_in, lease):
    from billing.models import MeterReading, UtilityType

    utility = UtilityType.objects.create(name="Water", measure="m3", rate_per_unit=50)
    response = logged_in.post(
        reverse("move_out_create", kwargs={"lease_pk": lease.pk}),
        {
            "notice_date": timezone.localdate().isoformat(),
            "move_out_date": (timezone.localdate() + timedelta(days=10)).isoformat(),
            "settlement_notes": "",
            f"reading_{utility.pk}": "125.00",
        },
    )
    assert response.status_code == 302
    move_out = MoveOut.objects.get(lease=lease)
    reading = MeterReading.objects.get(
        unit=lease.unit, utility_type=utility, reading_date=move_out.move_out_date
    )
    assert reading.reading_value == Decimal("125.00")


def test_prospect_create_and_convert(logged_in, building, floor):
    unit = Unit.objects.create(
        building=building, floor=floor, code="B01", base_rent=Decimal("1500.00")
    )
    response = logged_in.post(
        reverse("prospect_create"),
        {
            "name": "Bella",
            "business": "Salon Bella",
            "phone": "+254711111111",
            "email": "bella@example.com",
            "interested_unit": unit.pk,
            "status": "negotiating",
            "follow_up_date": timezone.localdate().isoformat(),
            "notes": "",
        },
    )
    assert response.status_code == 302
    prospect = Prospect.objects.get(name="Bella")

    response = logged_in.get(reverse("prospects"))
    assert response.status_code == 200
    assert b"Salon Bella" in response.content

    today = timezone.localdate()
    response = logged_in.post(
        reverse("prospect_convert", kwargs={"pk": prospect.pk}),
        {
            "unit": unit.pk,
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=365)).isoformat(),
            "monthly_rent": "1500.00",
            "deposit_amount": "3000.00",
            "escalation_type": "none",
            "escalation_value": "0",
            "status": "active",
            "notes": "",
        },
    )
    assert response.status_code == 302
    prospect.refresh_from_db()
    assert prospect.status == Prospect.STATUS_CONVERTED
    assert prospect.converted_lease is not None
    tenant = Tenant.objects.get(business_name="Salon Bella")
    assert tenant.contacts.filter(phone="+254711111111").exists()
    unit.refresh_from_db()
    assert unit.status == Unit.STATUS_OCCUPIED


def test_maintenance_creates_expense(logged_in, unit, tenant):
    response = logged_in.post(
        reverse("maintenance_create"),
        {
            "unit": unit.pk,
            "tenant": tenant.pk,
            "title": "Fix door",
            "description": "Door hinge loose",
            "priority": "urgent",
            "status": "open",
            "reported_date": timezone.localdate().isoformat(),
            "completed_date": "",
            "cost": "500.00",
        },
    )
    assert response.status_code == 302
    request_obj = MaintenanceRequest.objects.get(title="Fix door")

    category = ExpenseCategory.objects.create(name="Repairs")
    response = logged_in.get(reverse("expense_create") + f"?maintenance={request_obj.pk}")
    assert response.status_code == 200
    assert b"500.00" in response.content

    response = logged_in.post(
        reverse("expense_create"),
        {
            "category": category.pk,
            "expense_date": timezone.localdate().isoformat(),
            "amount": "500.00",
            "payee": "Fundi John",
            "description": "Fix door",
            "payment_method": "cash",
            "reference": "",
            "maintenance_request": request_obj.pk,
        },
    )
    assert response.status_code == 302
    expense = Expense.objects.get(payee="Fundi John")
    request_obj.refresh_from_db()
    assert request_obj.expense == expense
    assert request_obj.status == MaintenanceRequest.STATUS_DONE

    response = logged_in.get(reverse("maintenance_detail", kwargs={"pk": request_obj.pk}))
    assert response.status_code == 200


def test_expense_categories_and_receipt(logged_in, unit):
    response = logged_in.post(
        reverse("expense_categories"),
        {"name": "Utilities", "is_active": "on"},
    )
    assert response.status_code == 302
    category = ExpenseCategory.objects.get(name="Utilities")

    logged_in.post(
        reverse("expense_create"),
        {
            "category": category.pk,
            "expense_date": timezone.localdate().isoformat(),
            "amount": "250.00",
            "payee": "KPLC",
            "description": "Power",
            "payment_method": "mpesa",
            "reference": "REF1",
        },
    )
    expense = Expense.objects.get(payee="KPLC")
    response = logged_in.get(reverse("expense_detail", kwargs={"pk": expense.pk}))
    assert response.status_code == 200

    response = logged_in.post(
        reverse("expense_receipt_upload", kwargs={"pk": expense.pk}),
        {
            "doc_type": "receipt",
            "file": SimpleUploadedFile("receipt.pdf", b"%PDF-1.4", content_type="application/pdf"),
        },
    )
    assert response.status_code == 302
    document = Document.objects.get(owner_id=expense.pk)
    response = logged_in.post(reverse("expense_receipt_delete", kwargs={"pk": document.pk}))
    assert response.status_code == 302
    assert not Document.objects.filter(pk=document.pk).exists()

    logged_in.post(reverse("expense_category_toggle", kwargs={"pk": category.pk}))
    category.refresh_from_db()
    assert category.is_active is False


def test_full_lifecycle_prospect_to_refund(logged_in, building, floor):
    unit = Unit.objects.create(
        building=building, floor=floor, code="C01", base_rent=Decimal("1200.00")
    )
    today = timezone.localdate()

    logged_in.post(
        reverse("prospect_create"),
        {
            "name": "Amina",
            "business": "Amina Traders",
            "phone": "+254722222222",
            "email": "",
            "interested_unit": unit.pk,
            "status": "new",
            "follow_up_date": today.isoformat(),
            "notes": "",
        },
    )
    prospect = Prospect.objects.get(name="Amina")
    logged_in.post(
        reverse("prospect_convert", kwargs={"pk": prospect.pk}),
        {
            "unit": unit.pk,
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=365)).isoformat(),
            "monthly_rent": "1200.00",
            "deposit_amount": "2400.00",
            "escalation_type": "none",
            "escalation_value": "0",
            "status": "active",
            "notes": "",
        },
    )
    lease = Lease.objects.get(unit=unit)
    tenant = lease.tenant

    logged_in.post(
        reverse("lease_deposits", kwargs={"lease_pk": lease.pk}),
        {"amount_received": "2400.00", "received_date": today.isoformat()},
    )

    start = today.replace(day=1)
    end = add_months(start, 1) - timedelta(days=1)
    invoice, _ = generate_invoice(lease, start, end, today + timedelta(days=10))
    record_payment(
        tenant,
        today,
        "cash",
        Decimal("300.00"),
    )

    logged_in.post(
        reverse("move_out_create", kwargs={"lease_pk": lease.pk}),
        {
            "notice_date": today.isoformat(),
            "move_out_date": (today + timedelta(days=20)).isoformat(),
            "settlement_notes": "",
        },
    )
    move_out = MoveOut.objects.get(lease=lease)
    assert move_out.deposit_held == Decimal("2400.00")
    assert move_out.arrears_at_exit == Decimal("220.00")
    assert move_out.refund_amount == Decimal("2180.00")

    logged_in.post(reverse("move_out_settle", kwargs={"pk": move_out.pk}))
    move_out.refresh_from_db()
    lease.refresh_from_db()
    unit.refresh_from_db()
    assert move_out.status == MoveOut.STATUS_SETTLED
    assert lease.status == Lease.STATUS_TERMINATED
    assert unit.status == Unit.STATUS_VACANT
    assert lease.deposits.get().status == Deposit.STATUS_PARTLY_REFUNDED
    assert invoice.balance == Decimal("220.00")

def test_operations_management_pages_render(logged_in, lease, unit, tenant):
    from operations.models import Expense, ExpenseCategory, MaintenanceRequest, Prospect
    from operations.services import create_move_out, record_deposit
    from django.utils import timezone
    from decimal import Decimal

    assert logged_in.get(
        reverse("move_out_create", kwargs={"lease_pk": lease.pk})
    ).status_code == 200
    record_deposit(lease, "1000.00", timezone.localdate())
    move_out = create_move_out(lease, timezone.localdate() + timedelta(days=20))
    prospect = Prospect.objects.create(name="Test", business="Test Shop", interested_unit=unit)
    category = ExpenseCategory.objects.create(name="Rent")
    expense = Expense.objects.create(
        category=category,
        expense_date=timezone.localdate(),
        amount=Decimal("10.00"),
        payee="Test",
    )
    maintenance = MaintenanceRequest.objects.create(
        unit=unit,
        title="Test request",
        reported_date=timezone.localdate(),
    )

    urls = [
        reverse("prospects"),
        reverse("prospect_create"),
        reverse("prospect_edit", kwargs={"pk": prospect.pk}),
        reverse("prospect_convert", kwargs={"pk": prospect.pk}),
        reverse("move_outs"),
        reverse("move_out_detail", kwargs={"pk": move_out.pk}),
        reverse("lease_deposits", kwargs={"lease_pk": lease.pk}),
        reverse("maintenance"),
        reverse("maintenance_create"),
        reverse("maintenance_edit", kwargs={"pk": maintenance.pk}),
        reverse("maintenance_detail", kwargs={"pk": maintenance.pk}),
        reverse("expenses"),
        reverse("expense_create"),
        reverse("expense_edit", kwargs={"pk": expense.pk}),
        reverse("expense_detail", kwargs={"pk": expense.pk}),
        reverse("expense_categories"),
        reverse("expense_category_edit", kwargs={"pk": category.pk}),
    ]
    for url in urls:
        response = logged_in.get(url)
        assert response.status_code == 200, url
