"""Excel template generation, row validation and atomic import."""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from property.models import (
    Building,
    Floor,
    Lease,
    Tenant,
    TenantContact,
    Unit,
)
from property.services import (
    record_initial_rent,
    refresh_unit_statuses,
    validate_lease_fields,
)

COLUMNS = {
    "Buildings": ["name", "address", "notes"],
    "Floors": ["building", "name", "sort_order"],
    "Units": ["building", "floor", "code", "size_sqm", "base_rent", "status", "notes"],
    "Tenants": [
        "business_name",
        "trade",
        "id_or_kra_pin",
        "permit_number",
        "vat_applicable",
        "withholding_applicable",
        "primary_unit_code",
        "status",
        "notes",
        "contact_name",
        "contact_role",
        "contact_phone",
        "contact_email",
        "contact_primary",
    ],
    "Leases": [
        "unit_code",
        "tenant_business_name",
        "start_date",
        "end_date",
        "monthly_rent",
        "deposit_amount",
        "escalation_type",
        "escalation_value",
        "escalation_interval_months",
        "next_escalation_date",
        "status",
        "notes",
    ],
}

COLUMN_NOTES = {
    "Buildings": "name is required. Existing names are reused.",
    "Floors": "building must exist in this file or in the app. sort_order is optional.",
    "Units": "building and floor must exist. code is unique. status is vacant or reserved (occupied is automatic).",
    "Tenants": "business_name is required. primary_unit_code is optional. Dates use YYYY-MM-DD.",
    "Leases": "unit_code and tenant_business_name must exist in this file or the app. Only one active lease may overlap a unit.",
}

READ_ME_LINES = [
    "Rental Manager import template",
    "",
    "Fill the data sheets starting on row 2. Do not change the header rows.",
    "Every row is validated before anything is committed. If any row has an error, nothing is imported.",
    "Existing building, floor and tenant names are reused where the schema allows it. Units and leases are always new.",
    "Opening balances are imported after the billing phase, when invoices and credit exist.",
    "",
    "Sheets and columns:",
]

for sheet, columns in COLUMNS.items():
    READ_ME_LINES.append(f"- {sheet}: {', '.join(columns)}")
    READ_ME_LINES.append(f"  {COLUMN_NOTES[sheet]}")


class ImportFileError(Exception):
    """Raised when the workbook itself cannot be read or committed."""


@dataclass
class RowError:
    sheet: str
    row: int
    message: str


@dataclass
class ImportPreview:
    rows: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)

    @property
    def counts(self):
        return {sheet: len(self.rows.get(sheet, [])) for sheet in COLUMNS}

    @property
    def total_rows(self):
        return sum(self.counts.values())


def build_template_workbook() -> Workbook:
    workbook = Workbook()
    readme = workbook.active
    readme.title = "ReadMe"
    for index, line in enumerate(READ_ME_LINES, start=1):
        readme.cell(row=index, column=1, value=line)
    readme.column_dimensions["A"].width = 110
    readme["A1"].font = Font(bold=True, size=14)

    for sheet_name, columns in COLUMNS.items():
        sheet = workbook.create_sheet(sheet_name)
        sheet.append(columns)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for index, column in enumerate(columns, start=1):
            sheet.column_dimensions[get_column_letter(index)].width = max(14, len(column) + 4)
        sheet.freeze_panes = "A2"
    return workbook


def template_bytes() -> bytes:
    stream = BytesIO()
    build_template_workbook().save(stream)
    return stream.getvalue()


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _decimal(value, field_name, required=True, minimum=Decimal("0")):
    text = _text(value)
    if not text:
        if required:
            raise ValidationError(f"{field_name} is required.")
        return Decimal("0.00")
    try:
        amount = Decimal(text.replace(",", ""))
    except InvalidOperation as exc:
        raise ValidationError(f"{field_name} must be a number.") from exc
    if amount < minimum:
        raise ValidationError(f"{field_name} cannot be negative.")
    return amount.quantize(Decimal("0.01"))


def _integer(value, field_name, required=False, minimum=0):
    text = _text(value)
    if not text:
        if required:
            raise ValidationError(f"{field_name} is required.")
        return None
    try:
        number = int(float(text))
    except ValueError as exc:
        raise ValidationError(f"{field_name} must be a whole number.") from exc
    if number < minimum:
        raise ValidationError(f"{field_name} must be at least {minimum}.")
    return number


def _date(value, field_name, required=True):
    if value in (None, ""):
        if required:
            raise ValidationError(f"{field_name} is required.")
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _text(value)
    for pattern in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    raise ValidationError(f"{field_name} must be a date like YYYY-MM-DD.")


def _boolean(value, field_name="value") -> bool:
    text = _text(value).lower()
    if text in ("", "no", "n", "false", "0", "f"):
        return False
    if text in ("yes", "y", "true", "1", "t"):
        return True
    raise ValidationError(f"{field_name} must be yes or no.")


def _choice(value, field_name, allowed, default=None) -> str:
    text = _text(value).lower()
    if not text and default is not None:
        return default
    if text not in allowed:
        raise ValidationError(f"{field_name} must be one of: {', '.join(sorted(allowed))}.")
    return text


def _sheet_rows(workbook, sheet_name, errors):
    if sheet_name not in workbook.sheetnames:
        return []
    sheet = workbook[sheet_name]
    header_row = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ())
    header_values = [_text(value).lower() for value in header_row]
    header = {name: index for index, name in enumerate(header_values)}
    missing = [column for column in COLUMNS[sheet_name] if column not in header]
    if missing:
        errors.append(
            RowError(sheet_name, 1, f"Missing columns: {', '.join(missing)}.")
        )
        return []

    rows = []
    for row_number, row in enumerate(
        sheet.iter_rows(min_row=2, values_only=True), start=2
    ):
        values = {
            column: (row[header[column]] if header[column] < len(row) else None)
            for column in COLUMNS[sheet_name]
        }
        if all(not _text(value) for value in values.values()):
            continue
        rows.append((row_number, values))
    return rows


def parse_workbook(upload) -> ImportPreview:
    try:
        workbook = load_workbook(upload, data_only=True, read_only=True)
    except Exception as exc:  # noqa: BLE001 - surface a friendly message
        raise ImportFileError("The file is not a readable .xlsx workbook.") from exc

    errors = []
    rows = {sheet: _sheet_rows(workbook, sheet, errors) for sheet in COLUMNS}
    rows["_normalized_units"] = []
    rows["_normalized_tenants"] = []
    rows["_normalized_leases"] = []
    preview = ImportPreview(rows=rows, errors=errors)

    existing_buildings = Counter(Building.objects.values_list("name", flat=True))
    ambiguous_buildings = {name for name, count in existing_buildings.items() if count > 1}
    existing_floors = set(Floor.objects.values_list("building__name", "name"))
    existing_units = set(Unit.objects.values_list("code", flat=True))
    existing_tenants = Counter(Tenant.objects.values_list("business_name", flat=True))
    ambiguous_tenants = {name for name, count in existing_tenants.items() if count > 1}

    file_buildings = set()
    for row_number, values in rows["Buildings"]:
        name = _text(values["name"])
        if not name:
            preview.errors.append(RowError("Buildings", row_number, "name is required."))
            continue
        if name in ambiguous_buildings:
            preview.errors.append(
                RowError("Buildings", row_number, f"Building name '{name}' is ambiguous in the app.")
            )
            continue
        if name in file_buildings:
            preview.errors.append(
                RowError("Buildings", row_number, f"Duplicate building '{name}' in the file.")
            )
            continue
        file_buildings.add(name)

    file_floors = set()
    for row_number, values in rows["Floors"]:
        building_name = _text(values["building"])
        floor_name = _text(values["name"])
        if not building_name or not floor_name:
            preview.errors.append(
                RowError("Floors", row_number, "building and name are required.")
            )
            continue
        if building_name not in file_buildings and building_name not in existing_buildings:
            preview.errors.append(
                RowError("Floors", row_number, f"Unknown building '{building_name}'.")
            )
            continue
        if building_name in ambiguous_buildings:
            preview.errors.append(
                RowError("Floors", row_number, f"Building name '{building_name}' is ambiguous.")
            )
            continue
        key = (building_name, floor_name)
        if key in file_floors:
            preview.errors.append(
                RowError("Floors", row_number, f"Duplicate floor '{floor_name}' for {building_name}.")
            )
            continue
        file_floors.add(key)

    file_units = set()
    for row_number, values in rows["Units"]:
        try:
            building_name = _text(values["building"])
            floor_name = _text(values["floor"])
            code = _text(values["code"]).upper()
            if not building_name or not floor_name or not code:
                raise ValidationError("building, floor and code are required.")
            if building_name not in file_buildings and building_name not in existing_buildings:
                raise ValidationError(f"Unknown building '{building_name}'.")
            if building_name in ambiguous_buildings:
                raise ValidationError(f"Building name '{building_name}' is ambiguous.")
            if (building_name, floor_name) not in file_floors and (
                building_name,
                floor_name,
            ) not in existing_floors:
                raise ValidationError(f"Unknown floor '{floor_name}' for {building_name}.")
            if code in existing_units or code in file_units:
                raise ValidationError(f"Unit code '{code}' already exists.")
            status = _choice(
                values["status"],
                "status",
                {Unit.STATUS_VACANT, Unit.STATUS_RESERVED},
                default=Unit.STATUS_VACANT,
            )
            size_sqm = _decimal(values["size_sqm"], "size_sqm", required=False)
            base_rent = _decimal(values["base_rent"], "base_rent", required=True)
        except ValidationError as exc:
            preview.errors.append(RowError("Units", row_number, "; ".join(exc.messages)))
            continue
        file_units.add(code)
        preview.rows.setdefault("_normalized_units", []).append(
            {
                "row": row_number,
                "building": building_name,
                "floor": floor_name,
                "code": code,
                "size_sqm": size_sqm,
                "base_rent": base_rent,
                "status": status,
                "notes": _text(values["notes"]),
            }
        )

    file_tenants = set()
    for row_number, values in rows["Tenants"]:
        try:
            business_name = _text(values["business_name"])
            if not business_name:
                raise ValidationError("business_name is required.")
            if business_name in existing_tenants or business_name in file_tenants:
                raise ValidationError(f"Tenant '{business_name}' already exists.")
            status = _choice(
                values["status"],
                "status",
                {Tenant.STATUS_ACTIVE, Tenant.STATUS_FORMER},
                default=Tenant.STATUS_ACTIVE,
            )
            primary_unit_code = _text(values["primary_unit_code"]).upper()
            if primary_unit_code and (
                primary_unit_code not in file_units and primary_unit_code not in existing_units
            ):
                raise ValidationError(f"Unknown primary unit '{primary_unit_code}'.")
            vat_applicable = _boolean(values["vat_applicable"], "vat_applicable")
            withholding_applicable = _boolean(
                values["withholding_applicable"], "withholding_applicable"
            )
            contact_name = _text(values["contact_name"])
            contact_primary = True
            contact_email = _text(values["contact_email"])
            if contact_email:
                validate_email(contact_email)
            if contact_name:
                raw_primary = _text(values["contact_primary"])
                contact_primary = (
                    _boolean(raw_primary, "contact_primary") if raw_primary else True
                )
        except ValidationError as exc:
            preview.errors.append(RowError("Tenants", row_number, "; ".join(exc.messages)))
            continue
        file_tenants.add(business_name)
        preview.rows.setdefault("_normalized_tenants", []).append(
            {
                "row": row_number,
                "business_name": business_name,
                "trade": _text(values["trade"]),
                "id_or_kra_pin": _text(values["id_or_kra_pin"]),
                "permit_number": _text(values["permit_number"]),
                "vat_applicable": vat_applicable,
                "withholding_applicable": withholding_applicable,
                "primary_unit_code": primary_unit_code or None,
                "status": status,
                "notes": _text(values["notes"]),
                "contact_name": contact_name,
                "contact_role": _text(values["contact_role"]),
                "contact_phone": _text(values["contact_phone"]),
                "contact_email": contact_email,
                "contact_primary": contact_primary,
            }
        )

    active_intervals = defaultdict(list)
    for lease in Lease.objects.filter(status=Lease.STATUS_ACTIVE).values(
        "unit__code", "start_date", "end_date", "tenant__business_name"
    ):
        active_intervals[lease["unit__code"]].append(
            (lease["start_date"], lease["end_date"], lease["tenant__business_name"])
        )

    for row_number, values in rows["Leases"]:
        try:
            unit_code = _text(values["unit_code"]).upper()
            tenant_name = _text(values["tenant_business_name"])
            if not unit_code or not tenant_name:
                raise ValidationError("unit_code and tenant_business_name are required.")
            if unit_code not in file_units and unit_code not in existing_units:
                raise ValidationError(f"Unknown unit code '{unit_code}'.")
            if tenant_name not in file_tenants and tenant_name not in existing_tenants:
                raise ValidationError(f"Unknown tenant '{tenant_name}'.")
            if tenant_name in ambiguous_tenants:
                raise ValidationError(f"Tenant name '{tenant_name}' is ambiguous.")
            start = _date(values["start_date"], "start_date")
            end = _date(values["end_date"], "end_date")
            if end < start:
                raise ValidationError("end_date cannot be before start_date.")
            monthly_rent = _decimal(values["monthly_rent"], "monthly_rent")
            deposit = _decimal(values["deposit_amount"], "deposit_amount", required=False)
            escalation_type = _choice(
                values["escalation_type"],
                "escalation_type",
                {Lease.ESCALATION_NONE, Lease.ESCALATION_PERCENT, Lease.ESCALATION_FIXED},
                default=Lease.ESCALATION_NONE,
            )
            escalation_value = _decimal(
                values["escalation_value"], "escalation_value", required=False
            )
            interval = _integer(
                values["escalation_interval_months"], "escalation_interval_months"
            )
            next_date = _date(
                values["next_escalation_date"], "next_escalation_date", required=False
            )
            validate_lease_fields(escalation_type, escalation_value, interval, next_date)
            status = _choice(
                values["status"],
                "status",
                {
                    Lease.STATUS_DRAFT,
                    Lease.STATUS_ACTIVE,
                    Lease.STATUS_EXPIRED,
                    Lease.STATUS_TERMINATED,
                },
                default=Lease.STATUS_ACTIVE,
            )
            if status == Lease.STATUS_ACTIVE:
                for other_start, other_end, other_tenant in active_intervals[unit_code]:
                    if start <= other_end and end >= other_start:
                        raise ValidationError(
                            f"Active lease overlaps {other_tenant} "
                            f"({other_start:%d %b %Y} to {other_end:%d %b %Y})."
                        )
                active_intervals[unit_code].append((start, end, tenant_name))
        except ValidationError as exc:
            preview.errors.append(RowError("Leases", row_number, "; ".join(exc.messages)))
            continue
        preview.rows.setdefault("_normalized_leases", []).append(
            {
                "row": row_number,
                "unit_code": unit_code,
                "tenant_name": tenant_name,
                "start_date": start,
                "end_date": end,
                "monthly_rent": monthly_rent,
                "deposit_amount": deposit,
                "escalation_type": escalation_type,
                "escalation_value": escalation_value,
                "escalation_interval_months": interval,
                "next_escalation_date": next_date,
                "status": status,
                "notes": _text(values["notes"]),
            }
        )

    return preview


def commit_import(preview: ImportPreview) -> dict:
    if preview.errors:
        raise ImportFileError("Fix the row errors before importing.")
    if preview.total_rows == 0:
        raise ImportFileError("The workbook has no data rows.")

    counts = {}

    with transaction.atomic():
        buildings = {building.name: building for building in Building.objects.all()}
        for _row_number, row in preview.rows["Buildings"]:
            name = _text(row["name"])
            if name not in buildings:
                buildings[name] = Building.objects.create(
                    name=name,
                    address=_text(row.get("address")),
                    notes=_text(row.get("notes")),
                )

        floors = {
            (floor.building.name, floor.name): floor
            for floor in Floor.objects.select_related("building")
        }
        for _row_number, row in preview.rows["Floors"]:
            building_name = _text(row["building"])
            floor_name = _text(row["name"])
            key = (building_name, floor_name)
            if key not in floors:
                floors[key] = Floor.objects.create(
                    building=buildings[building_name],
                    name=floor_name,
                    sort_order=_integer(row.get("sort_order"), "sort_order") or 0,
                )

        units = {unit.code: unit for unit in Unit.objects.all()}
        for row in preview.rows["_normalized_units"]:
            unit = Unit(
                building=buildings[row["building"]],
                floor=floors[(row["building"], row["floor"])],
                code=row["code"],
                size_sqm=row["size_sqm"],
                base_rent=row["base_rent"],
                status=row["status"],
                notes=row["notes"],
            )
            unit.full_clean()
            unit.save()
            units[row["code"]] = unit

        tenants = {tenant.business_name: tenant for tenant in Tenant.objects.all()}
        for row in preview.rows["_normalized_tenants"]:
            primary_unit = units.get(row["primary_unit_code"]) if row["primary_unit_code"] else None
            tenant = Tenant(
                business_name=row["business_name"],
                trade=row["trade"],
                id_or_kra_pin=row["id_or_kra_pin"],
                permit_number=row["permit_number"],
                vat_applicable=row["vat_applicable"],
                withholding_applicable=row["withholding_applicable"],
                primary_unit=primary_unit,
                status=row["status"],
                notes=row["notes"],
            )
            tenant.full_clean()
            tenant.save()
            if row["contact_name"]:
                TenantContact.objects.create(
                    tenant=tenant,
                    name=row["contact_name"],
                    role_title=row["contact_role"],
                    phone=row["contact_phone"],
                    email=row["contact_email"],
                    is_primary=row["contact_primary"],
                )
            tenants[row["business_name"]] = tenant

        for row in preview.rows["_normalized_leases"]:
            lease = Lease(
                tenant=tenants[row["tenant_name"]],
                unit=units[row["unit_code"]],
                start_date=row["start_date"],
                end_date=row["end_date"],
                monthly_rent=row["monthly_rent"],
                deposit_amount=row["deposit_amount"],
                escalation_type=row["escalation_type"],
                escalation_value=row["escalation_value"],
                escalation_interval_months=row["escalation_interval_months"],
                next_escalation_date=row["next_escalation_date"],
                status=row["status"],
                notes=row["notes"],
            )
            lease.full_clean()
            lease.save()
            record_initial_rent(lease)

        refresh_unit_statuses()

        counts = {
            "Buildings": len(preview.rows["Buildings"]),
            "Floors": len(preview.rows["Floors"]),
            "Units": len(preview.rows["_normalized_units"]),
            "Tenants": len(preview.rows["_normalized_tenants"]),
            "Leases": len(preview.rows["_normalized_leases"]),
        }

    return counts
