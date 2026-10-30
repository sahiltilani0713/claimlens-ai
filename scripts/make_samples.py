"""
scripts/make_samples.py
Generates 6 synthetic PDF documents into sample_docs/ using ReportLab.
Run with:  python scripts/make_samples.py
All documents are fictional and for demo purposes only.
"""

import os
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas


# Output directory (relative to project root)
OUT_DIR = Path(__file__).resolve().parent.parent / "sample_docs"
OUT_DIR.mkdir(exist_ok=True)

# Page dimensions
PAGE_W, PAGE_H = A4


# ---------------------------------------------------------------------------
# Helper: draw a single PDF page
# ---------------------------------------------------------------------------

def make_pdf(filename: str, title: str, lines: list[str]) -> None:
    """Create one PDF file with a title, body lines, and a footer.

    Args:
        filename: Output filename (e.g. "loan_01_clean.pdf").
        title: Bold heading shown at the top of the page.
        lines: List of "Label: value" strings for the body.
    """
    path = OUT_DIR / filename
    c = canvas.Canvas(str(path), pagesize=A4)

    # --- Title ---
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 3 * cm, title)

    # Divider line under title
    c.setLineWidth(0.8)
    c.line(2 * cm, PAGE_H - 3.5 * cm, PAGE_W - 2 * cm, PAGE_H - 3.5 * cm)

    # --- Body: one "Label: value" line per row ---
    c.setFont("Helvetica", 12)
    y = PAGE_H - 5 * cm  # starting y position
    line_height = 0.8 * cm

    for line in lines:
        c.drawString(2 * cm, y, line)
        y -= line_height

    # --- Footer ---
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColorRGB(0.5, 0.5, 0.5)  # grey text
    c.drawCentredString(PAGE_W / 2, 1.5 * cm, "SYNTHETIC DOCUMENT - FOR DEMO ONLY")

    c.save()
    print(f"  Created: {path}")


# ---------------------------------------------------------------------------
# Document definitions
# ---------------------------------------------------------------------------

def generate_all() -> None:
    """Generate all 6 synthetic PDFs."""

    # 1. loan_01_clean.pdf – clean, plausible loan application
    make_pdf(
        "loan_01_clean.pdf",
        "Loan Application",
        [
            "Document Type: Loan Application",
            "Applicant Name: Ravi Kumar Sharma",
            "Application ID: LA-2026-0001",
            "Monthly Income: Rs. 60,000",
            "Loan Amount: Rs. 300,000",
            "Application Date: 05-01-2026",
            "Loan Start Date: 01-02-2026",
            "Loan End Date: 01-02-2031",
        ],
    )

    # 2. loan_02_missing_income.pdf – Monthly Income line absent
    make_pdf(
        "loan_02_missing_income.pdf",
        "Loan Application",
        [
            "Document Type: Loan Application",
            "Applicant Name: Priya Mehta",
            "Application ID: LA-2026-0002",
            # Monthly Income is intentionally missing
            "Loan Amount: Rs. 150,000",
            "Application Date: 10-02-2026",
            "Loan Start Date: 01-03-2026",
            "Loan End Date: 01-03-2029",
        ],
    )

    # 3. loan_03_high_ratio.pdf – loan amount >> income (risky ratio)
    make_pdf(
        "loan_03_high_ratio.pdf",
        "Loan Application",
        [
            "Document Type: Loan Application",
            "Applicant Name: Suresh Pillai",
            "Application ID: LA-2026-0003",
            "Monthly Income: Rs. 25,000",
            "Loan Amount: Rs. 2,500,000",
            "Application Date: 15-03-2026",
            "Loan Start Date: 01-04-2026",
            "Loan End Date: 01-04-2036",
        ],
    )

    # 4. loan_04_bad_dates.pdf – Loan End Date before Loan Start Date
    make_pdf(
        "loan_04_bad_dates.pdf",
        "Loan Application",
        [
            "Document Type: Loan Application",
            "Applicant Name: Anita Desai",
            "Application ID: LA-2026-0004",
            "Monthly Income: Rs. 45,000",
            "Loan Amount: Rs. 200,000",
            "Application Date: 20-04-2026",
            "Loan Start Date: 01-06-2026",
            "Loan End Date: 01-01-2026",   # end is before start – bad!
        ],
    )

    # 5. claim_01_normal.pdf – incident clearly after policy start
    make_pdf(
        "claim_01_normal.pdf",
        "Insurance Claim",
        [
            "Document Type: Insurance Claim",
            "Applicant Name: Deepa Nair",
            "Policy Number: POL-2025-5501",
            "Policy Start Date: 01-01-2025",
            "Incident Date: 15-06-2026",
            "Claim Amount: Rs. 40,000",
        ],
    )

    # 6. claim_02_suspicious.pdf – incident before policy start + huge amount
    make_pdf(
        "claim_02_suspicious.pdf",
        "Insurance Claim",
        [
            "Document Type: Insurance Claim",
            "Applicant Name: Vikram Bose",
            "Policy Number: POL-2026-7712",
            "Policy Start Date: 01-06-2026",
            "Incident Date: 15-03-2026",   # incident before policy – suspicious!
            "Claim Amount: Rs. 900,000",
        ],
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Generating PDFs into: {OUT_DIR}\n")
    try:
        generate_all()
        print("\nDone. All 6 files created.")
    except Exception as exc:
        print(f"ERROR: {exc}")
        raise
