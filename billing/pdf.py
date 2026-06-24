"""Generate commercial-document PDFs with ReportLab."""

from __future__ import annotations

import io
from decimal import Decimal

from django.http import HttpResponse
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from billing.models import CommercialDocument
from core.models import CompanySettings


def _money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):,.2f}"


def _money_cell(company: CompanySettings, value: Decimal) -> str:
    return f"{company.currency_code} {_money(value)}"


def _qr_drawing(value: str) -> Drawing:
    widget = qr.QrCodeWidget(value)
    bounds = widget.getBounds()
    size = 18 * mm
    drawing = Drawing(
        size,
        size,
        transform=[
            size / (bounds[2] - bounds[0]),
            0,
            0,
            size / (bounds[3] - bounds[1]),
            0,
            0,
        ],
    )
    drawing.add(widget)
    return drawing


def render_commercial_pdf(document: CommercialDocument, *, copy: bool = False) -> bytes:
    company = CompanySettings.load()
    buf = io.BytesIO()
    pdf_doc = SimpleDocTemplate(
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
    body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=9, spaceAfter=4)
    small = ParagraphStyle(
        "Small", parent=styles["Normal"], fontSize=8, textColor=colors.grey
    )

    story: list = []
    if company.logo:
        try:
            story.append(Image(company.logo.path, width=32 * mm, height=18 * mm))
        except (OSError, ValueError):
            pass
    story.append(Paragraph(company.company_name, h1))
    if company.tagline:
        story.append(Paragraph(company.tagline, small))
    address = [
        company.address_line,
        " ".join(
            value
            for value in (company.postal_code, company.city, company.region)
            if value
        ).strip(),
        company.country,
    ]
    story.append(Paragraph("<br/>".join(value for value in address if value), small))
    contacts = " · ".join(value for value in (company.phone, company.email) if value)
    if contacts:
        story.append(Paragraph(contacts, small))
    story.append(Spacer(1, 7 * mm))

    story.append(
        Paragraph(
            f"{document.get_doc_type_display().upper()} — {document.number}",
            styles["Heading2"],
        )
    )
    customer = document.display_customer_name
    if document.display_customer_company:
        customer += f" ({document.display_customer_company})"
    story.append(Paragraph(f"<b>Customer:</b> {customer}", body))
    customer_contacts = " · ".join(
        value
        for value in (
            document.display_customer_email,
            document.display_customer_phone,
        )
        if value
    )
    if customer_contacts:
        story.append(Paragraph(customer_contacts, body))
    if document.customer_address:
        story.append(Paragraph(document.customer_address.replace("\n", "<br/>"), body))

    metadata = [
        ["Issue date", str(document.issue_date)],
        ["Due / valid until", str(document.due_date or "—")],
        ["Status", document.get_status_display()],
        ["Pricing", document.get_pricing_mode_display()],
        ["Reference", document.contact_reference or "—"],
    ]
    metadata_table = Table(metadata, colWidths=[35 * mm, 90 * mm])
    metadata_table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(
        Table(
            [
                [
                    metadata_table,
                    _qr_drawing(
                        f"{document.number}|{document.total}|{document.issue_date}"
                    ),
                ]
            ],
            colWidths=[145 * mm, 22 * mm],
        )
    )
    story.append(Spacer(1, 5 * mm))
    if document.title:
        story.append(Paragraph(document.title, styles["Heading3"]))

    if document.hide_prices:
        data = [["Description", "Source", "Qty"]]
    else:
        data = [["Description", "Qty", "Unit", "Line total"]]
    for line in document.lines.all():
        details = " · ".join(
            value
            for value in (
                line.sku,
                line.serial_number,
                line.warranty,
                line.line_note,
            )
            if value
        )
        description = line.description
        if line.section:
            description = f"<b>{line.section}</b><br/>{description}"
        if details:
            description += f"<br/><font size='7' color='#666666'>{details}</font>"
        if document.hide_prices:
            data.append(
                [
                    Paragraph(description, body),
                    line.get_source_type_display(),
                    _money(line.quantity),
                ]
            )
        else:
            data.append(
                [
                    Paragraph(description, body),
                    _money(line.quantity),
                    _money_cell(company, line.unit_price),
                    _money_cell(company, line.line_total),
                ]
            )

    if not document.hide_prices:
        data.append(["", "", "Subtotal", _money_cell(company, document.subtotal)])
        if document.discount_amount:
            data.append(
                [
                    "",
                    "",
                    "Discount",
                    f"- {_money_cell(company, document.discount_amount)}",
                ]
            )
        if document.shipping_amount:
            data.append(
                ["", "", "Shipping", _money_cell(company, document.shipping_amount)]
            )
        if document.other_charges:
            data.append(
                [
                    "",
                    "",
                    document.other_charges_label or "Other charges",
                    _money_cell(company, document.other_charges),
                ]
            )
        data.append(["", "", "Tax", _money_cell(company, document.tax_amount)])
        if document.withholding_tax_amount:
            data.append(
                [
                    "",
                    "",
                    "Withholding",
                    f"- {_money_cell(company, document.withholding_tax_amount)}",
                ]
            )
        data.append(["", "", "Total", _money_cell(company, document.total)])
        if document.doc_type in (
            CommercialDocument.TYPE_INVOICE,
            CommercialDocument.TYPE_PROFORMA,
            CommercialDocument.TYPE_DEMAND_NOTE,
        ):
            data.append(
                ["", "", "Paid to date", _money_cell(company, document.amount_paid)]
            )
            data.append(
                ["", "", "Balance due", _money_cell(company, document.balance_due)]
            )

    table = Table(
        data,
        colWidths=(
            [105 * mm, 40 * mm, 25 * mm]
            if document.hide_prices
            else [85 * mm, 22 * mm, 28 * mm, 35 * mm]
        ),
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7f1ff")),
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
                ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f8f9fa")],
                ),
                ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#0d6efd")),
            ]
        )
    )
    story.append(table)
    if document.section_totals and not document.hide_prices:
        story.append(Spacer(1, 3 * mm))
        story.append(
            Table(
                [
                    [section["label"], _money_cell(company, section["total"])]
                    for section in document.section_totals
                ],
                colWidths=[100 * mm, 40 * mm],
                style=[
                    ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
                ],
            )
        )
    story.append(Spacer(1, 7 * mm))

    if document.notes:
        story.append(Paragraph("<b>Notes</b>", body))
        story.append(Paragraph(document.notes.replace("\n", "<br/>"), body))
    if document.terms:
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph("<b>Terms</b>", small))
        story.append(Paragraph(document.terms.replace("\n", "<br/>"), small))
    if document.tax_exempt and document.tax_exemption_reason:
        story.append(
            Paragraph(
                f"<b>Tax exemption:</b> {document.tax_exemption_reason}", small
            )
        )
    if company.bank_details:
        story.append(Spacer(1, 5 * mm))
        story.append(Paragraph("<b>Payment details</b>", small))
        story.append(Paragraph(company.bank_details.replace("\n", "<br/>"), small))
    approval_images = []
    for image_field in (company.signature_image, company.stamp_image):
        if not image_field:
            continue
        try:
            approval_images.append(
                Image(image_field.path, width=30 * mm, height=18 * mm)
            )
        except (OSError, ValueError):
            continue
    if approval_images or company.authorised_signatory:
        story.append(Spacer(1, 7 * mm))
        story.append(
            Table(
                [
                    approval_images
                    + [
                        Paragraph(
                            company.authorised_signatory or "Authorised signature",
                            small,
                        )
                    ]
                ],
                colWidths=[35 * mm] * (len(approval_images) + 1),
            )
        )
    if company.document_footer:
        story.append(Spacer(1, 5 * mm))
        story.append(Paragraph(company.document_footer.replace("\n", "<br/>"), small))

    def decorate_page(canvas, doc):
        watermark = "COPY" if copy else ""
        if not watermark and document.status == CommercialDocument.STATUS_DRAFT:
            watermark = "DRAFT"
        elif not watermark and document.status == CommercialDocument.STATUS_CANCELLED:
            watermark = "CANCELLED"
        if watermark:
            canvas.saveState()
            canvas.setFillColor(colors.Color(0.75, 0.75, 0.75, alpha=0.22))
            canvas.setFont("Helvetica-Bold", 58)
            canvas.translate(A4[0] / 2, A4[1] / 2)
            canvas.rotate(35)
            canvas.drawCentredString(0, 0, watermark)
            canvas.restoreState()
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.grey)
        canvas.drawRightString(
            A4[0] - 18 * mm, 8 * mm, f"{document.number} · page {doc.page}"
        )
        canvas.restoreState()

    pdf_doc.build(story, onFirstPage=decorate_page, onLaterPages=decorate_page)
    data = buf.getvalue()
    buf.close()
    return data


def pdf_response(
    document: CommercialDocument, inline: bool = False, *, copy: bool = False
) -> HttpResponse:
    data = render_commercial_pdf(document, copy=copy)
    response = HttpResponse(data, content_type="application/pdf")
    disposition = "inline" if inline else "attachment"
    response["Content-Disposition"] = (
        f'{disposition}; filename="{document.number}.pdf"'
    )
    return response
