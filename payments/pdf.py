"""Print-safe A4 receipts."""

import os
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.models import Settings

INK = colors.HexColor("#111111")
MUTED = colors.HexColor("#555555")
FAINT = colors.HexColor("#777777")
RULE = colors.HexColor("#cfcfcf")
HEADER_BG = colors.HexColor("#eeeeee")
DEFAULT_ACCENT = "#1d4ed8"


def _accent(settings_obj):
    value = (settings_obj.brand_color or "").strip()
    if len(value) == 7 and value.startswith("#"):
        try:
            int(value[1:], 16)
            return colors.HexColor(value)
        except ValueError:
            pass
    return colors.HexColor(DEFAULT_ACCENT)


def _styles():
    base = getSampleStyleSheet()
    return {
        "company": ParagraphStyle(
            "company", parent=base["Title"], fontName="Helvetica-Bold", fontSize=16,
            leading=19, textColor=INK, alignment=0, spaceAfter=2,
        ),
        "small": ParagraphStyle(
            "small", parent=base["BodyText"], fontName="Helvetica", fontSize=8.5,
            leading=11, textColor=MUTED,
        ),
        "body": ParagraphStyle(
            "body", parent=base["BodyText"], fontName="Helvetica", fontSize=9.5,
            leading=12.5, textColor=INK,
        ),
        "right": ParagraphStyle(
            "right", parent=base["BodyText"], fontName="Helvetica", fontSize=9,
            leading=12, textColor=MUTED, alignment=2,
        ),
        "title": ParagraphStyle(
            "title", parent=base["Title"], fontName="Helvetica-Bold", fontSize=22,
            leading=24, alignment=2, textColor=INK,
        ),
        "label": ParagraphStyle(
            "label", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=8,
            leading=10, textColor=FAINT,
        ),
        "cell": ParagraphStyle(
            "cell", parent=base["BodyText"], fontName="Helvetica", fontSize=8.5,
            leading=11, textColor=INK,
        ),
        "cell_right": ParagraphStyle(
            "cell_right", parent=base["BodyText"], fontName="Helvetica", fontSize=8.5,
            leading=11, textColor=INK, alignment=2,
        ),
        "head": ParagraphStyle(
            "head", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=7.5,
            leading=10, textColor=MUTED,
        ),
    }


def _logo(settings_obj):
    if not settings_obj.logo:
        return None
    try:
        path = settings_obj.logo.path
    except (ValueError, NotImplementedError):
        return None
    if not os.path.exists(path):
        return None
    try:
        width, height = ImageReader(path).getSize()
        max_width, max_height = 45 * mm, 18 * mm
        scale = min(max_width / width, max_height / height)
        return Image(path, width=width * scale, height=height * scale)
    except Exception:  # noqa: BLE001
        return None


def _money(amount, currency):
    return f"{currency} {amount:,.2f}"


def _footer(canvas, doc, settings_obj):
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, 18 * mm, A4[0] - doc.rightMargin, 18 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(FAINT)
    canvas.drawString(
        doc.leftMargin,
        13 * mm,
        f"{settings_obj.company_name} - computer generated receipt",
    )
    canvas.drawRightString(A4[0] - doc.rightMargin, 13 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_receipt_pdf(payment, settings_obj=None):
    settings_obj = settings_obj or Settings.load()
    styles = _styles()
    accent = _accent(settings_obj)
    currency = settings_obj.currency
    story = []

    company_parts = []
    logo = _logo(settings_obj)
    if logo is not None:
        company_parts.append(logo)
        company_parts.append(Spacer(1, 3 * mm))
    company_parts.append(Paragraph(escape(settings_obj.company_name), styles["company"]))
    if settings_obj.address:
        company_parts.append(
            Paragraph(escape(settings_obj.address).replace("\n", "<br/>"), styles["small"])
        )
    contact = "  |  ".join(
        bit for bit in (settings_obj.phone, settings_obj.email) if bit
    )
    if contact:
        company_parts.append(Paragraph(escape(contact), styles["small"]))
    if settings_obj.kra_pin:
        company_parts.append(
            Paragraph(f"KRA PIN: {escape(settings_obj.kra_pin)}", styles["small"])
        )

    right_parts = [
        Paragraph("RECEIPT", styles["title"]),
        Paragraph(f"<b>{escape(payment.receipt_number)}</b>", styles["right"]),
        Paragraph(f"Date received {payment.date_received:%d %b %Y}", styles["right"]),
        Paragraph(f"Method {payment.get_method_display()}", styles["right"]),
    ]
    if payment.reference:
        right_parts.append(Paragraph(f"Reference {escape(payment.reference)}", styles["right"]))
    if payment.is_void:
        right_parts.append(
            Paragraph(
                "<b>VOID</b>",
                ParagraphStyle(
                    "void", parent=styles["right"], textColor=colors.HexColor("#b91c1c")
                ),
            )
        )

    header = Table(
        [[company_parts, right_parts]],
        colWidths=[100 * mm, 80 * mm],
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        ),
    )
    story.append(header)
    story.append(Spacer(1, 3 * mm))
    rule = Table([[""]], colWidths=[180 * mm], rowHeights=[0.8 * mm])
    rule.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), accent)]))
    story.append(rule)
    story.append(Spacer(1, 4 * mm))

    if settings_obj.letterhead_text:
        story.append(
            Paragraph(
                escape(settings_obj.letterhead_text).replace("\n", "<br/>"),
                styles["small"],
            )
        )
        story.append(Spacer(1, 3 * mm))

    tenant = payment.tenant
    bill_to = [
        Paragraph("RECEIVED FROM", styles["label"]),
        Paragraph(escape(tenant.business_name), styles["body"]),
    ]
    if tenant.trade:
        bill_to.append(Paragraph(escape(tenant.trade), styles["small"]))
    if tenant.id_or_kra_pin:
        bill_to.append(
            Paragraph(f"ID / KRA PIN: {escape(tenant.id_or_kra_pin)}", styles["small"])
        )

    meta_parts = [Paragraph("PAYMENT", styles["label"])]
    if payment.method == payment.METHOD_CHEQUE:
        meta_parts.append(
            Paragraph(
                f"Cheque {escape(payment.cheque_number or '-')} &middot; "
                f"{escape(payment.cheque_bank or '-')} &middot; "
                f"{payment.get_cheque_status_display()}",
                styles["small"],
            )
        )
    if payment.withholding_amount:
        meta_parts.append(
            Paragraph(
                f"Withholding {_money(payment.withholding_amount, currency)}"
                + (
                    f" &middot; Cert {escape(payment.withholding_cert_no)}"
                    if payment.withholding_cert_no
                    else ""
                ),
                styles["small"],
            )
        )

    story.append(
        Table(
            [[bill_to, meta_parts]],
            colWidths=[100 * mm, 80 * mm],
            style=TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ]
            ),
        )
    )
    story.append(Spacer(1, 5 * mm))

    rows = [[
        Paragraph("Invoice", styles["head"]),
        Paragraph("Due", styles["head"]),
        Paragraph("Allocated", styles["head"]),
    ]]
    if payment.is_void:
        allocations = []
    else:
        allocations = payment.allocations.select_related("invoice").all()
    for allocation in allocations:
        rows.append(
            [
                Paragraph(escape(allocation.invoice.invoice_number), styles["cell"]),
                Paragraph(f"{allocation.invoice.due_date:%d %b %Y}", styles["cell"]),
                Paragraph(_money(allocation.amount, currency), styles["cell_right"]),
            ]
        )
    if not allocations:
        rows.append(
            [
                Paragraph("Credit carried forward", styles["cell"]),
                Paragraph("", styles["cell"]),
                Paragraph(_money(payment.settlement_amount, currency), styles["cell_right"]),
            ]
        )

    table = Table(rows, colWidths=[80 * mm, 50 * mm, 50 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, RULE),
                ("LINEBELOW", (0, 1), (-1, -1), 0.3, RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 4 * mm))

    summary = [["Cash received", _money(payment.amount, currency)]]
    if payment.withholding_amount:
        summary.append(
            ["Withholding tax", _money(payment.withholding_amount, currency)]
        )
    summary.append(["Total settled", _money(payment.settlement_amount, currency)])
    if payment.credit_amount:
        summary.append(["Credit carried forward", _money(payment.credit_amount, currency)])

    totals = Table(
        [
            [Paragraph(row[0], styles["cell_right"]), Paragraph(row[1], styles["cell_right"])]
            for row in summary
        ],
        colWidths=[50 * mm, 35 * mm],
        hAlign="RIGHT",
    )
    totals.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, 0), 0.4, RULE),
                ("LINEABOVE", (0, -1), (-1, -1), 0.8, INK),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(totals)
    story.append(Spacer(1, 6 * mm))
    story.append(
        Paragraph("Thank you. Keep this receipt for your records.", styles["small"])
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=24 * mm,
        title=payment.receipt_number,
        author=settings_obj.company_name,
    )
    doc.build(
        story,
        onFirstPage=lambda canvas, document: _footer(canvas, document, settings_obj),
        onLaterPages=lambda canvas, document: _footer(canvas, document, settings_obj),
    )
    buffer.seek(0)
    return buffer
