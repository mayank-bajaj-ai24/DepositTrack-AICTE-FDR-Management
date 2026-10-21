"""Release letter PDF (M9). Marked as a prototype document; in production it is e-signed."""

import io
from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

PROTOTYPE_MARK = "PROTOTYPE - NOT A VALID ORDER"


def render_release_letter(
    *,
    case_id: str,
    case_type: str,
    institution_name: str,
    aicte_id: str,
    fdr_no: str,
    ifsc: str,
    bank_name: str | None,
    amount: str,
    approved_by: str,
    reason: str,
    policy_version: str,
    issued_on: date,
) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    pdf.setTitle(f"{case_type.capitalize()} letter {case_id}")

    pdf.saveState()
    pdf.setFont("Helvetica-Bold", 36)
    pdf.setFillGray(0.85)
    pdf.translate(width / 2, height / 2)
    pdf.rotate(35)
    pdf.drawCentredString(0, 0, PROTOTYPE_MARK)
    pdf.restoreState()

    y = height - 30 * mm
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(25 * mm, y, f"Authorisation for {case_type} of security deposit / FDR")
    pdf.setFont("Helvetica", 10)
    lines = [
        f"Reference: DepositTrack case {case_id}",
        f"Date: {issued_on.isoformat()}",
        "",
        f"To: {bank_name or 'The Branch Manager'} (IFSC {ifsc})",
        "",
        f"Institution: {institution_name} (AICTE ID {aicte_id})",
        f"FDR number: {fdr_no}",
        f"Amount: Rs. {amount}",
        "",
        f"The competent authority has approved the {case_type} of the above instrument.",
        "You are requested to remove the lien marked in favour of AICTE and confirm.",
        "",
        f"Approved by: {approved_by}",
        f"Reason recorded: {reason}",
        f"Policy version applied: {policy_version}",
        "",
        PROTOTYPE_MARK,
    ]
    for line in lines:
        y -= 6 * mm
        pdf.drawString(25 * mm, y, line)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
