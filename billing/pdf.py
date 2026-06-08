"""Generate PDFs with ReportLab (no extra system dependencies on Windows)."""

from __future__ import annotations

import io
from decimal import Decimal

from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from billing.models import CommercialDocument
from core.models import CompanySettings


def _money(d: Decimal) -> str:
    return f"{d.quantize(Decimal('0.01')):,.2f}"


def _money_cell(company: CompanySettings, d: Decimal) -> str:
    return f"{company.currency_code} {_money(d)}"


def render_commercial_pdf(document: CommercialDocument) -> bytes:
    company = CompanySettings.load()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=document.number,
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle(
        "H1",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=6,
        textColor=colors.HexColor("#0d6efd"),
    )
    body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=10, spaceAfter=4)
    small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, textColor=colors.grey)

    story: list = []
    story.append(Paragraph(company.company_name, h1))
    if company.tagline:
        story.append(Paragraph(company.tagline, small))
    addr_bits = [
        company.address_line,
        " ".join(
            x
            for x in (company.postal_code, company.city, company.region)
            if x
        ).strip(),
        company.country,
    ]
    story.append(Paragraph("<br/>".join(x for x in addr_bits if x), small))
    if company.phone or company.email:
        story.append(
            Paragraph(
                " · ".join(x for x in (company.phone, company.email) if x),
                small,
            )
        )
    story.append(Spacer(1, 8 * mm))

    kind = document.get_doc_type_display().upper()
    story.append(Paragraph(f"{kind} — {document.number}", styles["Heading2"]))
    story.append(
        Paragraph(
            f"<b>Bill to:</b> {document.customer.name}"
            + (
                f" ({document.customer.company_name})"
                if document.customer.company_name
                else ""
            ),
            body,
        )
    )
    story.append(
        Paragraph(
            f"{document.customer.email}"
            + (f" · {document.customer.phone}" if document.customer.phone else ""),
            body,
        )
    )
    story.append(Spacer(1, 4 * mm))

    meta = [
        ["Issue date", str(document.issue_date)],
        ["Due date", str(document.due_date or "—")],
        ["Status", document.get_status_display()],
    ]
    t_meta = Table(meta, colWidths=[35 * mm, 120 * mm])
    t_meta.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(t_meta)
    story.append(Spacer(1, 6 * mm))

    if document.title:
        story.append(Paragraph(document.title, styles["Heading3"]))

    data = [["Description", "Qty", "Unit", "Line total"]]
    for line in document.lines.all():
        data.append(
            [
                line.description,
                _money(line.quantity),
                _money_cell(company, line.unit_price),
                _money_cell(company, line.line_total),
            ]
        )
    data.append(["", "", "Subtotal", _money_cell(company, document.subtotal)])
    data.append(["", "", f"Tax ({document.tax_rate}%)", _money_cell(company, document.tax_amount)])
    data.append(["", "", "Total", _money_cell(company, document.total)])
    if document.doc_type in (
        CommercialDocument.TYPE_INVOICE,
        CommercialDocument.TYPE_PROFORMA,
        CommercialDocument.TYPE_DEMAND_NOTE,
    ):
        data.append(["", "", "Paid to date", _money_cell(company, document.amount_paid)])
        data.append(["", "", "Balance due", _money_cell(company, document.balance_due)])

    tbl = Table(
        data,
        colWidths=[85 * mm, 22 * mm, 28 * mm, 35 * mm],
    )
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7f1ff")),
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
                ("FONT", (0, 1), (-1, -4), "Helvetica", 9),
                ("FONT", (0, -3), (-1, -1), "Helvetica-Bold", 9),
                ("LINEABOVE", (0, -3), (-1, -3), 0.5, colors.grey),
                ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#0d6efd")),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -4), [colors.white, colors.HexColor("#f8f9fa")]),
            ]
        )
    )
    story.append(tbl)
    story.append(Spacer(1, 8 * mm))

    if document.doc_type == CommercialDocument.TYPE_RECEIPT:
        payments = list(document.payments.all()[:10])
        story.append(Paragraph("Payment summary", styles["Heading3"]))
        if payments:
            pdata = [["Date", "Method", "Reference", "Amount"]]
            for p in payments:
                pdata.append(
                    [
                        p.recorded_at.strftime("%Y-%m-%d %H:%M"),
                        p.get_method_display(),
                        p.reference or "—",
                        _money_cell(company, p.amount),
                    ]
                )
            pt = Table(pdata, colWidths=[35 * mm, 30 * mm, 55 * mm, 35 * mm])
            pt.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f3f5")),
                        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
                        ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
                        ("ALIGN", (-1, 1), (-1, -1), "RIGHT"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
                    ]
                )
            )
            story.append(pt)
        else:
            story.append(Paragraph("No payments recorded.", body))
        story.append(Spacer(1, 6 * mm))

    if document.notes:
        story.append(Paragraph("<b>Notes</b>", body))
        story.append(Paragraph(document.notes.replace("\n", "<br/>"), body))
    if document.terms:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph("<b>Terms</b>", small))
        story.append(Paragraph(document.terms.replace("\n", "<br/>"), small))
    if company.bank_details:
        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph("<b>Bank / payment details</b>", small))
        story.append(Paragraph(company.bank_details.replace("\n", "<br/>"), small))

    doc.build(story)
    pdf = buf.getvalue()
    buf.close()
    return pdf


def pdf_response(document: CommercialDocument, inline: bool = False) -> HttpResponse:
    data = render_commercial_pdf(document)
    resp = HttpResponse(data, content_type="application/pdf")
    disp = "inline" if inline else "attachment"
    resp["Content-Disposition"] = f'{disp}; filename="{document.number}.pdf"'
    return resp
