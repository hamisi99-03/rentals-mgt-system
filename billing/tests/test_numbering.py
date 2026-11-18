from decimal import Decimal

import pytest
from django.db import transaction
from django.utils import timezone

from billing.services import generate_invoice, parse_period
from core.models import NumberSequence
from core.numbering import format_document_number, next_document_number
from property.models import Unit

pytestmark = pytest.mark.django_db


def test_number_format_uses_settings(unit, settings_obj):
    assert format_document_number("invoice", unit.code, 1, settings_obj) == "INV-A01-0001"

    settings_obj.invoice_prefix = "BILL"
    settings_obj.number_separator = "/"
    settings_obj.number_padding = 5
    settings_obj.save()
    assert format_document_number("invoice", unit.code, 12, settings_obj) == "BILL/A01/00012"


def test_sequences_are_per_unit_and_per_document_type(unit, building, floor, settings_obj):
    other = Unit.objects.create(
        building=building, floor=floor, code="A02", base_rent=Decimal("1000")
    )
    assert next_document_number("invoice", unit, settings_obj) == "INV-A01-0001"
    assert next_document_number("invoice", unit, settings_obj) == "INV-A01-0002"
    assert next_document_number("invoice", other, settings_obj) == "INV-A02-0001"

    settings_obj.receipt_prefix = "RCT"
    settings_obj.save()
    assert next_document_number("receipt", unit, settings_obj) == "RCT-A01-0001"
    assert next_document_number("receipt", unit, settings_obj) == "RCT-A01-0002"


def test_rolled_back_number_is_not_consumed(unit, settings_obj):
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            assert next_document_number("invoice", unit, settings_obj) == "INV-A01-0001"
            raise RuntimeError("boom")

    assert NumberSequence.objects.filter(unit=unit, doc_type="invoice").count() == 0
    assert next_document_number("invoice", unit, settings_obj) == "INV-A01-0001"


def test_invoice_uses_unit_number_and_is_unique(lease, settings_obj):
    period_start, period_end = parse_period("2026-01")
    first, created = generate_invoice(
        lease, period_start, period_end, timezone.localdate()
    )
    assert created is True
    assert first.invoice_number == "INV-A01-0001"

    second, created = generate_invoice(
        lease, period_start, period_end, timezone.localdate()
    )
    assert created is False
    assert second is None
