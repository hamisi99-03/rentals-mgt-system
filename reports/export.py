"""Excel and print-safe PDF exports for report tables."""

from datetime import date
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.models import Settings

INK = colors.HexColor("#111111")
MUTED = colors.HexColor("#555555")
FAINT = colors.HexColor("#777777")
RULE = colors.HexColor("#cfcfcf")
HEADER_BG = colors.HexColor("#eeeeee")


def _display(value):
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{value:,.2f}"
    if isinstance(value, date):
        return value.strftime("%d %b %Y")
    return escape(str(value))


def _excel(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


def _footer(canvas, doc, settings_obj):
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, 12 * mm, doc.pagesize[0] - doc.rightMargin, 12 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(FAINT)
    canvas.drawString(
        doc.leftMargin, 8 * mm, f"{settings_obj.company_name} - report"
    )
    canvas.drawRightString(
        doc.pagesize[0] - doc.rightMargin, 8 * mm, f"Page {doc.page}"
    )
    canvas.restoreState()


def build_table_pdf(title, headers, rows, subtitle="", totals=None, col_widths=None):
    settings_obj = Settings.load()
    base = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "report-title", parent=base["Title"], fontName="Helvetica-Bold",
        fontSize=16, leading=19, textColor=INK, alignment=0,
    )
    meta_style = ParagraphStyle(
        "report-meta", parent=base["BodyText"], fontName="Helvetica",
        fontSize=8.5, leading=11, textColor=MUTED,
    )
    head_style = ParagraphStyle(
        "report-head", parent=base["BodyText"], fontName="Helvetica-Bold",
        fontSize=7.5, leading=10, textColor=MUTED,
    )
    cell_style = ParagraphStyle(
        "report-cell", parent=base["BodyText"], fontName="Helvetica",
        fontSize=8, leading=10.5, textColor=INK,
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4) if len(headers) > 5 else A4,
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=12 * mm,
        bottomMargin=18 * mm,
        title=title,
        author=settings_obj.company_name,
    )

    story = [
        Paragraph(escape(settings_obj.company_name), ParagraphStyle(
            "company", parent=title_style, fontSize=10, leading=12, textColor=FAINT,
        )),
        Paragraph(escape(title), title_style),
    ]
    if subtitle:
        story.append(Paragraph(escape(subtitle), meta_style))
    story.append(
        Paragraph(
            f"Generated {timezone.localtime():%d %b %Y %H:%M}", meta_style
        )
    )
    story.append(Spacer(1, 4 * mm))

    data = [[Paragraph(_display(header), head_style) for header in headers]]
    for row in rows:
        data.append([Paragraph(_display(value), cell_style) for value in row])
    if totals:
        data.append([Paragraph(f"<b>{_display(value)}</b>", cell_style) for value in totals])

    available = doc.width
    if col_widths is None:
        col_widths = [available / len(headers)] * len(headers)
    table = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, RULE),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]
    if totals:
        style.append(("BACKGROUND", (0, -1), (-1, -1), HEADER_BG))
        style.append(("LINEABOVE", (0, -1), (-1, -1), 0.8, INK))
    table.setStyle(TableStyle(style))
    story.append(table)

    doc.build(
        story,
        onFirstPage=lambda canvas, document: _footer(canvas, document, settings_obj),
        onLaterPages=lambda canvas, document: _footer(canvas, document, settings_obj),
    )
    buffer.seek(0)
    return buffer


def build_table_xlsx(title, headers, rows, totals=None):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Report"
    sheet.append([title])
    sheet["A1"].font = Font(bold=True, size=14)
    sheet.append([])
    sheet.append(headers)
    for cell in sheet[3]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append([_excel(value) for value in row])
    if totals:
        sheet.append([_excel(value) for value in totals])
        for cell in sheet[sheet.max_row]:
            cell.font = Font(bold=True)
    for index, header in enumerate(headers, start=1):
        width = max(12, len(str(header)) + 4)
        sheet.column_dimensions[get_column_letter(index)].width = width
    stream = BytesIO()
    workbook.save(stream)
    stream.seek(0)
    return stream
