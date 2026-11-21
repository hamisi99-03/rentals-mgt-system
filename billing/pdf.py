"""Print-safe invoice PDFs using ReportLab.

The PDF palette is fixed and light, never the dark theme, per docs/THEMES.md.
"""

import os
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from core.models import Settings

INK = colors.HexColor("#111111")
MUTED = colors.HexColor("#555555")
FAINT = colors.HexColor("#777777")
RULE = colors.HexColor("#cfcfcf")
HEADER_BG = colors.HexColor("#eeeeee")
WHITE = colors.white
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


def _money(amount, currency):
    return f"{currency} {amount:,.2f}"


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
        "label": ParagraphStyle(
            "label", parent=base["BodyText"], fontName="Helvetica-Bold", fontSize=8,
            leading=10, textColor=FAINT,
        ),
        "title": ParagraphStyle(
            "title", parent=base["Title"], fontName="Helvetica-Bold", fontSize=22,
            leading=24, alignment=2, textColor=INK,
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
    except Exception:  # noqa: BLE001 - a bad logo must not break the PDF
        return None


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
        f"{settings_obj.company_name} - computer generated document",
    )
    canvas.drawRightString(A4[0] - doc.rightMargin, 13 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _invoice_story(invoice, settings_obj, styles, accent):
    currency = settings_obj.currency
    has_vat = any(line.vat_amount and line.vat_amount != 0 for line in invoice.lines.all())
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
    contact_bits = [settings_obj.phone, settings_obj.email]
    contact = "  |  ".join(bit for bit in contact_bits if bit)
    if contact:
        company_parts.append(Paragraph(escape(contact), styles["small"]))
    if settings_obj.kra_pin:
        company_parts.append(
            Paragraph(f"KRA PIN: {escape(settings_obj.kra_pin)}", styles["small"])
        )

    right_parts = [Paragraph("INVOICE", styles["title"])]
    right_parts.append(
        Paragraph(f"<b>{escape(invoice.invoice_number)}</b>", styles["right"])
    )
    right_parts.append(
        Paragraph(
            f"Issued {invoice.issue_date:%d %b %Y} &nbsp;&nbsp; Due {invoice.due_date:%d %b %Y}",
            styles["right"],
        )
    )
    right_parts.append(
        Paragraph(
            f"Period {invoice.period_start:%d %b %Y} - {invoice.period_end:%d %b %Y}",
            styles["right"],
        )
    )
    if invoice.is_void:
        right_parts.append(
            Paragraph("<b>VOID</b>", ParagraphStyle(
                "void", parent=styles["right"], textColor=colors.HexColor("#b91c1c"),
            ))
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

    bill_to = [
        Paragraph("BILL TO", styles["label"]),
        Paragraph(escape(invoice.tenant.business_name), styles["body"]),
    ]
    if invoice.tenant.trade:
        bill_to.append(Paragraph(escape(invoice.tenant.trade), styles["small"]))
    if invoice.tenant.id_or_kra_pin:
        bill_to.append(
            Paragraph(f"ID / KRA PIN: {escape(invoice.tenant.id_or_kra_pin)}", styles["small"])
        )

    property_bits = [
        Paragraph("PROPERTY", styles["label"]),
        Paragraph(f"Unit {escape(invoice.unit.code)}", styles["body"]),
        Paragraph(
            escape(f"{invoice.unit.building.name} / {invoice.unit.floor.name}"),
            styles["small"],
        ),
        Paragraph(
            (
                f"Lease {invoice.lease.start_date:%d %b %Y} - "
                f"{invoice.lease.end_date:%d %b %Y}"
                if invoice.lease.end_date
                else f"Monthly rental from {invoice.lease.start_date:%d %b %Y}"
            ),
            styles["small"],
        ),
    ]
    bill_table = Table(
        [[bill_to, property_bits]],
        colWidths=[100 * mm, 80 * mm],
        style=TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        ),
    )
    story.append(bill_table)
    story.append(Spacer(1, 5 * mm))

    headers = ["Description", "Qty", "Unit price", "Amount"]
    if has_vat:
        headers.append("VAT")
    rows = [[Paragraph(label, styles["head"]) for label in headers]]
    for line in invoice.lines.all():
        quantity = f"{line.quantity:g}" if line.quantity is not None else ""
        row = [
            Paragraph(escape(line.description), styles["cell"]),
            Paragraph(quantity, styles["cell_right"]),
            Paragraph(_money(line.unit_price, currency), styles["cell_right"]),
            Paragraph(_money(line.amount, currency), styles["cell_right"]),
        ]
        if has_vat:
            row.append(Paragraph(_money(line.vat_amount, currency), styles["cell_right"]))
        rows.append(row)

    widths = [80 * mm, 16 * mm, 30 * mm, 30 * mm]
    if has_vat:
        widths.append(24 * mm)
    line_table = Table(rows, colWidths=widths, repeatRows=1)
    line_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, RULE),
                ("LINEBELOW", (0, 1), (-1, -1), 0.3, RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, 0), 3),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 3),
                ("TOPPADDING", (0, 1), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(line_table)
    story.append(Spacer(1, 4 * mm))

    totals_rows = [["Subtotal", _money(invoice.subtotal, currency)]]
    if has_vat:
        totals_rows.append(
            [f"VAT ({invoice.vat_rate_snapshot:g}%)", _money(invoice.vat_amount, currency)]
        )
    totals_rows.append(["Total due", _money(invoice.total, currency)])
    totals = Table(
        [
            [Paragraph(row[0], styles["cell_right"]), Paragraph(row[1], styles["cell_right"])]
            for row in totals_rows
        ],
        colWidths=[45 * mm, 35 * mm],
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
        Paragraph(
            "Please pay by the due date. Quote the invoice number with your payment.",
            styles["small"],
        )
    )
    return story


def build_invoice_pdf(invoice, settings_obj=None):
    settings_obj = settings_obj or Settings.load()
    styles = _styles()
    accent = _accent(settings_obj)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=24 * mm,
        title=invoice.invoice_number,
        author=settings_obj.company_name,
    )
    story = _invoice_story(invoice, settings_obj, styles, accent)
    doc.build(
        story,
        onFirstPage=lambda canvas, document: _footer(canvas, document, settings_obj),
        onLaterPages=lambda canvas, document: _footer(canvas, document, settings_obj),
    )
    buffer.seek(0)
    return buffer


def build_invoices_pdf(invoices, settings_obj=None):
    settings_obj = settings_obj or Settings.load()
    styles = _styles()
    accent = _accent(settings_obj)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=24 * mm,
        title="Invoices",
        author=settings_obj.company_name,
    )
    story = []
    for index, invoice in enumerate(invoices):
        if index:
            story.append(PageBreak())
        story.extend(_invoice_story(invoice, settings_obj, styles, accent))
    doc.build(
        story,
        onFirstPage=lambda canvas, document: _footer(canvas, document, settings_obj),
        onLaterPages=lambda canvas, document: _footer(canvas, document, settings_obj),
    )
    buffer.seek(0)
    return buffer
