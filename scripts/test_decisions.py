"""
scripts/test_decisions.py
Runs the full Phase-3 pipeline on every PDF in sample_docs/ and prints
the recommendation and reasons for each file.
"""

from pathlib import Path

from claimlens.extraction import PDFExtractor
from claimlens.validation import Validator
from claimlens.rules import DecisionEngine

# Paths
SAMPLE_DIR = Path(__file__).parent.parent / "sample_docs"

extractor = PDFExtractor()
validator = Validator()
engine = DecisionEngine()


def process_file(pdf_path: Path) -> None:
    """Extract, validate, decide, and print results for one PDF."""
    print(f"\n{'=' * 60}")
    print(f"FILE: {pdf_path.name}")
    print("=" * 60)

    # Step 1: Extract text and fields
    text = extractor.extract_text(pdf_path)
    fields = extractor.extract_fields(text)

    # Step 2: Validate fields
    val_findings = validator.validate(fields)

    # Step 3: Run decision engine
    decision = engine.decide(fields, val_findings)

    # Step 4: Print results
    print(f"  {decision.recommendation}")
    print("\n  Reasons:")
    for reason in decision.reasons[1:]:  # skip the summary line (already printed above)
        print(f"    - {reason}")


def main() -> None:
    pdfs = sorted(SAMPLE_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDF files found in {SAMPLE_DIR}")
        return

    for pdf in pdfs:
        process_file(pdf)

    print(f"\n{'=' * 60}")
    print(f"Done. Processed {len(pdfs)} file(s).")


if __name__ == "__main__":
    main()
