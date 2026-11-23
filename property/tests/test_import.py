from datetime import timedelta
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook, load_workbook

from property.import_export import COLUMNS, parse_workbook
from property.models import Building, Floor, Lease, Tenant, TenantContact, Unit

pytestmark = pytest.mark.django_db


def make_workbook(rows_by_sheet):
    workbook = Workbook()
    workbook.remove(workbook.active)
    for sheet_name, columns in COLUMNS.items():
        sheet = workbook.create_sheet(sheet_name)
        sheet.append(columns)
        for row in rows_by_sheet.get(sheet_name, []):
            sheet.append([row.get(column, "") for column in columns])
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def upload(client, content, name="import.xlsx"):
    return client.post(
        reverse("import_data"),
        {
            "file": SimpleUploadedFile(
                name,
                content,
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )


def sample_rows(count=40):
    today = timezone.localdate()
    rows = {
        "Buildings": [{"name": "Mwangaza Plaza", "address": "Ngong Road", "notes": ""}],
        "Floors": [
            {"building": "Mwangaza Plaza", "name": "Ground floor", "sort_order": 0},
            {"building": "Mwangaza Plaza", "name": "First floor", "sort_order": 1},
        ],
        "Units": [],
        "Tenants": [],
        "Leases": [],
    }
    for index in range(1, count + 1):
        code = f"A{index:02d}"
        tenant_name = f"Tenant {index:02d}"
        rows["Units"].append(
            {
                "building": "Mwangaza Plaza",
                "floor": "Ground floor" if index % 2 else "First floor",
                "code": code,
                "size_sqm": "24.00",
                "base_rent": "25000.00",
                "status": "vacant",
                "notes": "",
            }
        )
        rows["Tenants"].append(
            {
                "business_name": tenant_name,
                "trade": "Retail",
                "id_or_kra_pin": f"KRA{index:03d}",
                "permit_number": f"P{index:03d}",
                "vat_applicable": "no",
                "withholding_applicable": "no",
                "primary_unit_code": code,
                "status": "active",
                "notes": "",
                "contact_name": f"Contact {index:02d}",
                "contact_role": "Owner",
                "contact_phone": f"+25470000{index:04d}",
                "contact_email": "",
                "contact_primary": "yes",
            }
        )
        rows["Leases"].append(
            {
                "unit_code": code,
                "tenant_business_name": tenant_name,
                "start_date": (today - timedelta(days=30)).isoformat(),
                "end_date": (today + timedelta(days=335)).isoformat(),
                "monthly_rent": "25000.00",
                "deposit_amount": "50000.00",
                "escalation_type": "none",
                "escalation_value": "0",
                "escalation_interval_months": "",
                "next_escalation_date": "",
                "status": "active",
                "notes": "",
            }
        )
    return rows


def test_template_download_has_expected_sheets(logged_in):
    response = logged_in.get(reverse("import_template"))
    assert response.status_code == 200
    assert response["Content-Type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    workbook = load_workbook(BytesIO(response.content))
    assert "ReadMe" in workbook.sheetnames
    for sheet, columns in COLUMNS.items():
        assert sheet in workbook.sheetnames
        headers = [cell.value for cell in workbook[sheet][1]]
        assert headers == columns


def test_sample_workbook_downloads_and_validates(logged_in):
    response = logged_in.get(reverse("import_sample"))
    assert response.status_code == 200
    assert response["Content-Type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    preview = parse_workbook(BytesIO(response.content))
    assert preview.errors == []
    assert preview.counts == {
        "Buildings": 2,
        "Floors": 4,
        "Units": 40,
        "Tenants": 40,
        "Leases": 40,
    }


def test_import_forty_units_tenants_and_leases(logged_in):
    rows = sample_rows(40)
    response = upload(logged_in, make_workbook(rows))
    assert response.status_code == 200
    assert b"Import complete" in response.content

    assert Building.objects.count() == 1
    assert Floor.objects.count() == 2
    assert Unit.objects.count() == 40
    assert Tenant.objects.count() == 40
    assert TenantContact.objects.count() == 40
    assert Lease.objects.count() == 40
    assert Lease.objects.filter(rent_history__reason="initial").count() == 40
    assert Unit.objects.filter(status=Unit.STATUS_OCCUPIED).count() == 40


def test_import_rejects_rows_and_commits_nothing(logged_in):
    rows = sample_rows(2)
    rows["Units"][1]["code"] = rows["Units"][0]["code"]
    response = upload(logged_in, make_workbook(rows))
    assert response.status_code == 200
    assert b"Nothing was imported" in response.content or b"Nothing was imported" in response.content
    assert Building.objects.count() == 0
    assert Unit.objects.count() == 0
    assert Lease.objects.count() == 0


def test_import_rejects_overlapping_active_leases(logged_in):
    rows = sample_rows(1)
    second = dict(rows["Leases"][0])
    second["tenant_business_name"] = "Tenant 01"
    second["start_date"] = (timezone.localdate() - timedelta(days=10)).isoformat()
    second["end_date"] = (timezone.localdate() + timedelta(days=100)).isoformat()
    rows["Leases"].append(second)

    response = upload(logged_in, make_workbook(rows))
    assert response.status_code == 200
    assert b"overlaps" in response.content or b"Overlaps" in response.content
    assert Lease.objects.count() == 0
    assert Unit.objects.count() == 0


def test_import_reuses_existing_building_and_floor(logged_in):
    building = Building.objects.create(name="Mwangaza Plaza")
    floor = Floor.objects.create(building=building, name="Ground floor")
    rows = sample_rows(1)
    response = upload(logged_in, make_workbook(rows))
    assert response.status_code == 200
    assert Building.objects.count() == 1
    assert Floor.objects.filter(building=building, name="Ground floor").count() == 1
    assert Unit.objects.count() == 1
    assert Unit.objects.get().floor_id == floor.pk


def test_import_rejects_non_xlsx_extension(logged_in):
    response = upload(logged_in, b"not excel", name="import.csv")
    assert response.status_code == 200
    assert Unit.objects.count() == 0


def test_import_rejects_corrupt_workbook(logged_in):
    response = upload(logged_in, b"not really excel", name="broken.xlsx")
    assert response.status_code == 200
    assert Unit.objects.count() == 0


def test_import_reports_missing_columns(logged_in):
    workbook = Workbook()
    workbook.remove(workbook.active)
    sheet = workbook.create_sheet("Units")
    sheet.append(["building", "floor", "code"])
    stream = BytesIO()
    workbook.save(stream)

    response = upload(logged_in, stream.getvalue())
    assert response.status_code == 200
    assert b"Missing columns" in response.content
    assert Unit.objects.count() == 0


def test_import_requires_login(client):
    response = client.get(reverse("import_data"))
    assert response.status_code == 302
