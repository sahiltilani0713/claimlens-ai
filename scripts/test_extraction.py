"""
scripts/test_extraction.py
Runs PDFExtractor on every PDF in sample_docs/ and prints a summary table.
Run with:  python scripts/test_extraction.py
"""

import sys
from pathlib import Path

import pandas as pd

# Allow imports from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from claimlens.extraction import PDFExtractor

# Locate all PDFs in sample_docs/
SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_docs"


def main() -> None:
    """Extract fields from each sample PDF and display results as a table."""
    extractor = PDFExtractor()
    rows = []

    pdf_files = sorted(SAMPLE_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDFs found in {SAMPLE_DIR}")
        return

    for pdf_path in pdf_files:
        text = extractor.extract_text(pdf_path)
        if not text:
            # PDF was empty or unreadable
            rows.append({
                "file": pdf_path.name,
                "field": "—",
                "value": "UNREADABLE",
                "confidence": 0.0,
                "status": "missing",
            })
            continue

        fields = extractor.extract_fields(text)
        for field_key, ef in fields.items():
            rows.append({
                "file": pdf_path.name,
                "field": field_key,
                "value": ef.value if ef.value is not None else "(none)",
                "confidence": ef.confidence,
                "status": ef.status,
            })

    # Build and print the DataFrame
    df = pd.DataFrame(rows, columns=["file", "field", "value", "confidence", "status"])
    pd.set_option("display.max_rows", 200)
    pd.set_option("display.max_colwidth", 40)
    pd.set_option("display.width", 120)
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
