"""ESC/POS thermal receipt (plain text, ignores themes)."""

import os

from escpos.printer import Dummy

from core.models import Settings
from payments.models import Payment


def _line(label, value, width=42):
    text = f"{label}: {value}"
    return text[:width] + "\n"


def build_thermal_receipt(payment: Payment, settings_obj=None) -> bytes:
    settings_obj = settings_obj or Settings.load()
    printer = Dummy()
    printer._raw(b"\x1b@")
    currency = settings_obj.currency

    printer.set(align="center", bold=True, double_height=True, double_width=True)
    printer.text(f"{settings_obj.company_name}\n")
    printer.set(align="center", bold=False, double_height=False, double_width=False)
    if settings_obj.address:
        printer.text(f"{settings_obj.address}\n")
    contact = " | ".join(
        bit for bit in (settings_obj.phone, settings_obj.email) if bit
    )
    if contact:
        printer.text(f"{contact}\n")
    if settings_obj.kra_pin:
        printer.text(f"KRA PIN: {settings_obj.kra_pin}\n")

    if settings_obj.logo:
        try:
            path = settings_obj.logo.path
            if os.path.exists(path):
                printer.image(path)
        except Exception:  # noqa: BLE001 - thermal printing must not fail on a bad logo
            pass

    printer.text("\n")
    printer.set(align="center", bold=True)
    printer.text("RECEIPT\n")
    printer.set(align="left", bold=False)
    printer.text(f"Receipt: {payment.receipt_number}\n")
    printer.text(f"Date: {payment.date_received:%d %b %Y}\n")
    printer.text(f"Tenant: {payment.tenant.business_name}\n")
    printer.text(f"Method: {payment.get_method_display()}\n")
    if payment.reference:
        printer.text(f"Reference: {payment.reference}\n")
    if payment.method == Payment.METHOD_CHEQUE:
        printer.text(
            f"Cheque: {payment.cheque_number or '-'} {payment.cheque_bank or ''}\n"
        )
        printer.text(f"Cheque status: {payment.get_cheque_status_display()}\n")
    if payment.is_void:
        printer.set(align="center", bold=True)
        printer.text("*** VOID ***\n")
        printer.set(align="left", bold=False)

    printer.text("-" * 42 + "\n")
    if not payment.is_void:
        for allocation in payment.allocations.select_related("invoice"):
            printer.text(f"{allocation.invoice.invoice_number}\n")
            printer.text(
                f"  Due {allocation.invoice.due_date:%d %b %Y}  "
                f"{currency} {allocation.amount:,.2f}\n"
            )
    else:
        printer.text("Allocations reversed\n")

    printer.text("-" * 42 + "\n")
    printer.text(_line("Cash received", f"{currency} {payment.amount:,.2f}"))
    if payment.withholding_amount:
        printer.text(
            _line("Withholding", f"{currency} {payment.withholding_amount:,.2f}")
        )
        if payment.withholding_cert_no:
            printer.text(_line("WHT cert", payment.withholding_cert_no))
    printer.set(bold=True)
    printer.text(_line("Total settled", f"{currency} {payment.settlement_amount:,.2f}"))
    printer.set(bold=False)
    if payment.credit_amount:
        printer.text(
            _line("Credit forward", f"{currency} {payment.credit_amount:,.2f}")
        )

    printer.text("\n")
    printer.set(align="center")
    printer.text("Thank you. Keep this receipt.\n")
    printer.text("\n\n")
    printer.cut()
    return printer.output or b""
