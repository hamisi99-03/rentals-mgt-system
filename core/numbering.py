"""Atomic document numbering: {PREFIX}-{UNITCODE}-{SEQ:0p}."""

from django.db import IntegrityError, transaction

from core.models import NumberSequence, Settings


def format_document_number(doc_type: str, unit_code: str, value: int, settings_obj=None) -> str:
    settings_obj = settings_obj or Settings.load()
    if doc_type == NumberSequence.DOC_INVOICE:
        prefix = settings_obj.invoice_prefix
    elif doc_type == NumberSequence.DOC_RECEIPT:
        prefix = settings_obj.receipt_prefix
    else:
        raise ValueError(f"Unknown document type: {doc_type}")

    separator = settings_obj.number_separator or "-"
    parts = []
    if prefix:
        parts.append(prefix)
    if unit_code:
        parts.append(unit_code)
    parts.append(f"{value:0{settings_obj.number_padding}d}")
    return separator.join(parts)


def next_document_number(doc_type: str, unit, settings_obj=None) -> str:
    """Reserve the next number. Call inside the transaction that saves the document.

    The sequence row is locked and incremented in the same transaction, so a
    rolled-back invoice does not consume a number and a committed one cannot be
    reused.
    """
    with transaction.atomic():
        try:
            sequence = NumberSequence.objects.select_for_update().get(
                doc_type=doc_type, unit=unit
            )
        except NumberSequence.DoesNotExist:
            try:
                sequence = NumberSequence.objects.create(
                    doc_type=doc_type, unit=unit, last_value=0
                )
            except IntegrityError:
                sequence = NumberSequence.objects.select_for_update().get(
                    doc_type=doc_type, unit=unit
                )
            else:
                sequence = NumberSequence.objects.select_for_update().get(pk=sequence.pk)

        sequence.last_value += 1
        sequence.save(update_fields=["last_value", "updated_at"])
        return format_document_number(
            doc_type, unit.code, sequence.last_value, settings_obj
        )
