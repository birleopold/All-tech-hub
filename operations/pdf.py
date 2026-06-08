"""Job card PDFs with ReportLab (Windows-friendly, no system deps)."""

from __future__ import annotations

import io

from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.models import CompanySettings
from operations.models import JobCard


def render_jobcard_pdf(job: JobCard) -> bytes:
    company = CompanySettings.load()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=job.number or "Job Card",
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
    small = ParagraphStyle(
        "Small", parent=styles["Normal"], fontSize=8, textColor=colors.grey
    )

    story: list = []
    story.append(Paragraph(company.company_name, h1))
    if company.tagline:
        story.append(Paragraph(company.tagline, small))
    if company.phone or company.email:
        story.append(
            Paragraph(
                " · ".join(x for x in (company.phone, company.email) if x),
                small,
            )
        )
    story.append(Spacer(1, 8 * mm))

    story.append(Paragraph(f"JOB CARD — {job.number}", styles["Heading2"]))
    story.append(Paragraph(job.title, body))
    story.append(Spacer(1, 3 * mm))

    meta = [
        ["Customer", job.customer.name],
        ["Email", job.customer.email],
        ["Phone", job.customer.phone or "—"],
        ["Status", job.get_status_display()],
        ["Priority", job.get_priority_display()],
        ["Received", job.received_on.strftime("%Y-%m-%d %H:%M")],
        [
            "Assigned to",
            job.assigned_to.get_username() if job.assigned_to else "—",
        ],
        ["ETA", str(job.estimated_completion or "—")],
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

    device = [
        ["Device type", job.device_type or "—"],
        ["Make / model", f"{job.device_make} {job.device_model}".strip() or "—"],
        ["Serial number", job.serial_number or "—"],
        ["Accessories received", job.accessories_received or "—"],
    ]
    t_dev = Table(device, colWidths=[35 * mm, 120 * mm])
    t_dev.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
            ]
        )
    )
    story.append(Paragraph("Device details", styles["Heading3"]))
    story.append(t_dev)
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("Problem reported", styles["Heading3"]))
    story.append(Paragraph((job.problem_reported or "—").replace("\n", "<br/>"), body))
    story.append(Spacer(1, 3 * mm))

    story.append(Paragraph("Diagnosis", styles["Heading3"]))
    story.append(Paragraph((job.diagnosis or "—").replace("\n", "<br/>"), body))
    story.append(Spacer(1, 3 * mm))

    story.append(Paragraph("Resolution", styles["Heading3"]))
    story.append(Paragraph((job.resolution or "—").replace("\n", "<br/>"), body))

    doc.build(story)
    pdf = buf.getvalue()
    buf.close()
    return pdf


def pdf_response(job: JobCard, inline: bool = True) -> HttpResponse:
    data = render_jobcard_pdf(job)
    resp = HttpResponse(data, content_type="application/pdf")
    disp = "inline" if inline else "attachment"
    filename = job.number or "job-card"
    resp["Content-Disposition"] = f'{disp}; filename="{filename}.pdf"'
    return resp

