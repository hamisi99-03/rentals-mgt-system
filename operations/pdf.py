"""Print-safe move-out settlement PDF."""

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
            "title", parent=base["Title"], fontName="Helvetica-Bold", fontSize=19,
            leading=22, alignment=2, textColor=INK,
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
        f"{settings_obj.company_name} - move-out settlement",
    )
    canvas.drawRightString(A4[0] - doc.rightMargin, 13 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_move_out_pdf(move_out, settings_obj=None):
    settings_obj = settings_obj or Settings.load()
    styles = _styles()
    accent = _accent(settings_obj)
    currency = settings_obj.currency
    lease = move_out.lease
    tenant = lease.tenant
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
        Paragraph("MOVE-OUT SETTLEMENT", styles["title"]),
        Paragraph(f"Move-out {move_out.move_out_date:%d %b %Y}", styles["right"]),
        Paragraph(f"Status {move_out.get_status_display()}", styles["right"]),
    ]

    header = Table(
        [[company_parts, right_parts]],
        colWidths=[110 * mm, 70 * mm],
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

    tenant_parts = [
        Paragraph("TENANT", styles["label"]),
        Paragraph(escape(tenant.business_name), styles["body"]),
    ]
    if tenant.trade:
        tenant_parts.append(Paragraph(escape(tenant.trade), styles["small"]))
    property_parts = [
        Paragraph("UNIT", styles["label"]),
        Paragraph(f"Unit {escape(lease.unit.code)}", styles["body"]),
        Paragraph(
            escape(f"{lease.unit.building.name} / {lease.unit.floor.name}"),
            styles["small"],
        ),
        Paragraph(
            (
                f"Lease {lease.start_date:%d %b %Y} - {lease.end_date:%d %b %Y}"
                if lease.end_date
                else f"Monthly rental from {lease.start_date:%d %b %Y}"
            ),
            styles["small"],
        ),
    ]
    story.append(
        Table(
            [[tenant_parts, property_parts]],
            colWidths=[90 * mm, 90 * mm],
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

    story.append(Paragraph("Checklist", styles["label"]))
    rows = [[
        Paragraph("Item", styles["head"]),
        Paragraph("Condition", styles["head"]),
        Paragraph("Damage", styles["head"]),
        Paragraph("Notes", styles["head"]),
    ]]
    for item in move_out.items.all():
        rows.append(
            [
                Paragraph(item.get_item_display(), styles["cell"]),
                Paragraph(escape(item.condition), styles["cell"]),
                Paragraph(_money(item.damage_cost, currency), styles["cell_right"]),
                Paragraph(escape(item.notes), styles["cell"]),
            ]
        )
    table = Table(rows, colWidths=[40 * mm, 35 * mm, 35 * mm, 70 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, RULE),
                ("LINEBELOW", (0, 1), (-1, -1), 0.3, RULE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 4 * mm))

    readings = lease.unit.meter_readings.filter(
        reading_date=move_out.move_out_date
    ).select_related("utility_type")
    if readings:
        story.append(Paragraph("Final meter readings", styles["label"]))
        rows = [[
            Paragraph("Utility", styles["head"]),
            Paragraph("Previous", styles["head"]),
            Paragraph("Reading", styles["head"]),
            Paragraph("Consumption", styles["head"]),
        ]]
        for reading in readings:
            rows.append(
                [
                    Paragraph(escape(reading.utility_type.name), styles["cell"]),
                    Paragraph(f"{reading.previous_value:.2f}", styles["cell_right"]),
                    Paragraph(
                        f"{reading.reading_value:.2f} {escape(reading.utility_type.measure)}",
                        styles["cell_right"],
                    ),
                    Paragraph(f"{reading.consumption:.2f}", styles["cell_right"]),
                ]
            )
        reading_table = Table(rows, colWidths=[55 * mm, 35 * mm, 45 * mm, 45 * mm])
        reading_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.5, RULE),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.3, RULE),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(reading_table)
        story.append(Spacer(1, 4 * mm))

    summary_rows = [
        ["Deposit held", _money(move_out.deposit_held, currency)],
        ["Less arrears", f"- {_money(move_out.arrears_at_exit, currency)}"],
        ["Less damages", f"- {_money(move_out.damages_amount, currency)}"],
        ["Refund due", _money(move_out.refund_amount, currency)],
    ]
    totals = Table(
        [
            [Paragraph(row[0], styles["cell_right"]), Paragraph(row[1], styles["cell_right"])]
            for row in summary_rows
        ],
        colWidths=[50 * mm, 40 * mm],
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
    story.append(Spacer(1, 3 * mm))
    if move_out.remaining_balance > 0:
        story.append(
            Paragraph(
                f"Balance remaining after deposit: "
                f"<b>{_money(move_out.remaining_balance, currency)}</b>",
                styles["body"],
            )
        )
        story.append(Spacer(1, 3 * mm))
    if move_out.settlement_notes:
        story.append(Paragraph("Notes", styles["label"]))
        story.append(
            Paragraph(
                escape(move_out.settlement_notes).replace("\n", "<br/>"),
                styles["small"],
            )
        )
        story.append(Spacer(1, 5 * mm))

    signature = Table(
        [[
            Paragraph("Tenant signature: ____________________", styles["small"]),
            Paragraph("Owner signature: ____________________", styles["small"]),
        ]],
        colWidths=[90 * mm, 90 * mm],
    )
    story.append(signature)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=24 * mm,
        title=f"Move-out {lease.unit.code}",
        author=settings_obj.company_name,
    )
    doc.build(
        story,
        onFirstPage=lambda canvas, document: _footer(canvas, document, settings_obj),
        onLaterPages=lambda canvas, document: _footer(canvas, document, settings_obj),
    )
    buffer.seek(0)
    return buffer
