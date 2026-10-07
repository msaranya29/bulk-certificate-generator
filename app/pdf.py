"""Single predefined certificate template, rendered with reportlab."""
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas


def render_certificate(path: str, name: str, course_name: str, issuer: str,
                       issue_date: str, certificate_id: str) -> None:
    width, height = landscape(A4)
    c = canvas.Canvas(path, pagesize=landscape(A4))
    c.setTitle(f"Certificate - {name}")

    c.setStrokeColor(colors.HexColor("#1a3a6b"))
    c.setLineWidth(6)
    c.rect(25, 25, width - 50, height - 50)
    c.setLineWidth(1.5)
    c.rect(40, 40, width - 80, height - 80)

    c.setFillColor(colors.HexColor("#1a3a6b"))
    c.setFont("Helvetica-Bold", 38)
    c.drawCentredString(width / 2, height - 130, "Certificate of Completion")

    c.setFillColor(colors.black)
    c.setFont("Helvetica", 16)
    c.drawCentredString(width / 2, height - 190, "This is to certify that")

    c.setFont("Helvetica-Bold", 32)
    c.drawCentredString(width / 2, height - 245, name)
    c.line(width / 2 - 200, height - 255, width / 2 + 200, height - 255)

    c.setFont("Helvetica", 16)
    c.drawCentredString(width / 2, height - 295, "has successfully completed")
    c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(width / 2, height - 335, course_name)

    c.setFont("Helvetica", 13)
    c.drawString(80, 90, f"Date: {issue_date}")
    c.drawRightString(width - 80, 90, f"Issued by: {issuer}")
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.grey)
    c.drawCentredString(width / 2, 55, f"Certificate ID: {certificate_id}")
    c.showPage()
    c.save()
