"""
claimlens/extraction.py
Extracts structured fields from loan and insurance claim PDFs.
No ML -- pure regex + rule-based confidence scoring.
"""

import re
import datetime
from pathlib import Path

import pdfplumber

from claimlens.models import ExtractedField


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def parse_amount(text: str) -> float | None:
    """Convert a currency string like 'Rs. 45,000' to a float.

    Strips the 'Rs.' prefix and commas, then converts to float.
    Returns None if no valid number is found.

    Args:
        text: Raw string from the PDF line.

    Returns:
        Numeric amount, or None on failure.
    """
    # Remove currency prefix, spaces, commas; keep digits and decimal point
    cleaned = re.sub(r"[Rr]s\.?\s*", "", text)
    cleaned = cleaned.replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_date(text: str) -> datetime.date | None:
    """Parse a DD-MM-YYYY date string into a datetime.date object.

    Returns None if the string does not match the expected format
    or represents an impossible date (e.g. month 13).

    Args:
        text: Raw string that should contain a date.

    Returns:
        A datetime.date object, or None on failure.
    """
    # Match exactly DD-MM-YYYY
    match = re.search(r"(\d{2})-(\d{2})-(\d{4})", text.strip())
    if not match:
        return None
    try:
        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        return datetime.date(year, month, day)
    except ValueError:
        # Invalid calendar date (e.g. 30-02-2026)
        return None


# ---------------------------------------------------------------------------
# PDFExtractor class
# ---------------------------------------------------------------------------

class PDFExtractor:
    """Extracts and scores fields from loan and insurance claim PDFs.

    Confidence rules:
      1.0 -- Exact label regex matched AND format check passed (amount/date/name/ID valid).
      0.7 -- Only the fallback (loose) regex matched AND format check passed.
      0.4 -- Any regex matched but the format check failed (raw text kept as value).
      0.0 -- Nothing matched; status set to "missing", value set to None.

    Status rules:
      "verified"     -- confidence >= 0.9
      "needs_review" -- 0.0 < confidence < 0.9
      "missing"      -- confidence == 0.0
    """

    # -----------------------------------------------------------------------
    # Field definitions: (exact_pattern, fallback_pattern, validator_type)
    # validator_type is one of: "amount", "date", "name", "id"
    # -----------------------------------------------------------------------

    # Loan fields
    LOAN_FIELDS: dict[str, tuple[str, str, str]] = {
        "applicant_name": (
            r"Applicant Name:\s*(.+)",                               # exact: "Applicant Name:"
            r"(?:applicant|name|borrower)[:\s]+(.+)",                # fallback: any name-like label
            "name",
        ),
        "application_id": (
            r"Application ID:\s*(.+)",                               # exact: "Application ID:"
            r"(?:application|app|ref)[.\s]*(?:id|no|number)[:\s]+(.+)",  # fallback
            "id",
        ),
        "monthly_income": (
            r"Monthly Income:\s*(.+)",                               # exact: "Monthly Income:"
            r"(?:monthly\s*income|income|salary|earnings)[:\s]+(.+)",    # fallback
            "amount",
        ),
        "loan_amount": (
            r"Loan Amount:\s*(.+)",                                  # exact: "Loan Amount:"
            r"(?:loan\s*amount|amount\s*of\s*loan|loan)[:\s]+(.+)", # fallback
            "amount",
        ),
        "application_date": (
            r"Application Date:\s*(.+)",                             # exact: "Application Date:"
            r"(?:application\s*date|app\s*date|date\s*of\s*application)[:\s]+(.+)",  # fallback
            "date",
        ),
        "loan_start_date": (
            r"Loan Start Date:\s*(.+)",                              # exact: "Loan Start Date:"
            r"(?:loan\s*start|start\s*date|disbursement\s*date)[:\s]+(.+)",  # fallback
            "date",
        ),
        "loan_end_date": (
            r"Loan End Date:\s*(.+)",                                # exact: "Loan End Date:"
            r"(?:loan\s*end|end\s*date|maturity\s*date)[:\s]+(.+)", # fallback
            "date",
        ),
    }

    # Claim fields
    CLAIM_FIELDS: dict[str, tuple[str, str, str]] = {
        "applicant_name": (
            r"Applicant Name:\s*(.+)",                               # exact: "Applicant Name:"
            r"(?:applicant|claimant|name)[:\s]+(.+)",                # fallback
            "name",
        ),
        "policy_number": (
            r"Policy Number:\s*(.+)",                                # exact: "Policy Number:"
            r"(?:policy\s*(?:number|no|id)|pol)[:\s]+(.+)",         # fallback
            "id",
        ),
        "policy_start_date": (
            r"Policy Start Date:\s*(.+)",                            # exact: "Policy Start Date:"
            r"(?:policy\s*start|start\s*date|commencement\s*date)[:\s]+(.+)",  # fallback
            "date",
        ),
        "incident_date": (
            r"Incident Date:\s*(.+)",                                # exact: "Incident Date:"
            r"(?:incident\s*date|date\s*of\s*(?:incident|loss|accident))[:\s]+(.+)",  # fallback
            "date",
        ),
        "claim_amount": (
            r"Claim Amount:\s*(.+)",                                 # exact: "Claim Amount:"
            r"(?:claim\s*amount|amount\s*claimed|claimed)[:\s]+(.+)",  # fallback
            "amount",
        ),
    }

    # -----------------------------------------------------------------------
    # Public methods
    # -----------------------------------------------------------------------

    def extract_text(self, path: str | Path) -> str:
        """Open a PDF and return all its text as a single string.

        Handles missing files, corrupted PDFs, and empty documents
        gracefully by returning an empty string on any failure.

        Args:
            path: Path to the PDF file.

        Returns:
            Extracted text, or "" on failure.
        """
        try:
            with pdfplumber.open(str(path)) as pdf:
                pages = [page.extract_text() or "" for page in pdf.pages]
                text = "\n".join(pages).strip()
                return text
        except FileNotFoundError:
            return ""
        except Exception:
            # Catches corrupted, password-protected, or unreadable PDFs
            return ""

    def detect_doc_type(self, text: str) -> str:
        """Detect whether this document is a loan application or insurance claim.

        Looks for the "Document Type:" line and checks its value.

        Args:
            text: Full text extracted from the PDF.

        Returns:
            "loan", "claim", or "unknown".
        """
        # Match the Document Type label (case-insensitive)
        match = re.search(r"Document Type:\s*(.+)", text, re.IGNORECASE)
        if match:
            doc_type_value = match.group(1).strip().lower()
            if "loan" in doc_type_value:
                return "loan"
            if "claim" in doc_type_value or "insurance" in doc_type_value:
                return "claim"
        return "unknown"

    def extract_fields(self, text: str) -> dict[str, ExtractedField]:
        """Extract all relevant fields from the document text.

        Selects the field definitions based on the detected doc type,
        then runs exact -> fallback regex matching and scores confidence.

        Args:
            text: Full text extracted from the PDF.

        Returns:
            Dict mapping field key to ExtractedField dataclass.
        """
        doc_type = self.detect_doc_type(text)

        # Pick the right field set based on doc type
        if doc_type == "loan":
            field_defs = self.LOAN_FIELDS
        elif doc_type == "claim":
            field_defs = self.CLAIM_FIELDS
        else:
            return {}  # Cannot extract fields for unknown doc types

        results: dict[str, ExtractedField] = {}

        for field_key, (exact_pat, fallback_pat, validator) in field_defs.items():
            extracted = self._match_field(text, field_key, exact_pat, fallback_pat, validator)
            results[field_key] = extracted

        return results

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _match_field(
        self,
        text: str,
        field_key: str,
        exact_pat: str,
        fallback_pat: str,
        validator: str,
    ) -> ExtractedField:
        """Try exact regex, then fallback regex; score confidence accordingly.

        Args:
            text:         Full document text.
            field_key:    Internal field name (e.g. "monthly_income").
            exact_pat:    Regex with one capture group; case-sensitive.
            fallback_pat: Looser regex; applied case-insensitively.
            validator:    One of "amount", "date", "name", "id".

        Returns:
            An ExtractedField with value, confidence, status, source_text.
        """
        # Step 1: Try the exact label pattern first
        exact_match = re.search(exact_pat, text)
        if exact_match:
            raw = exact_match.group(1).strip()
            source_line = self._find_source_line(text, raw)
            if self._format_valid(raw, validator):
                # Best case: exact match + valid format
                return ExtractedField(
                    name=field_key,
                    value=raw,
                    confidence=1.0,
                    status="verified",
                    source_text=source_line,
                )
            else:
                # Exact match but format check failed
                return ExtractedField(
                    name=field_key,
                    value=raw,
                    confidence=0.4,
                    status="needs_review",
                    source_text=source_line,
                )

        # Step 2: Try the looser fallback pattern (case-insensitive)
        fallback_match = re.search(fallback_pat, text, re.IGNORECASE)
        if fallback_match:
            raw = fallback_match.group(1).strip()
            source_line = self._find_source_line(text, raw)
            if self._format_valid(raw, validator):
                # Fallback matched + valid format
                return ExtractedField(
                    name=field_key,
                    value=raw,
                    confidence=0.7,
                    status="needs_review",
                    source_text=source_line,
                )
            else:
                # Fallback matched but format check failed
                return ExtractedField(
                    name=field_key,
                    value=raw,
                    confidence=0.4,
                    status="needs_review",
                    source_text=source_line,
                )

        # Step 3: Nothing matched -- field is missing
        return ExtractedField(
            name=field_key,
            value=None,
            confidence=0.0,
            status="missing",
            source_text="",
        )

    def _format_valid(self, raw: str, validator: str) -> bool:
        """Check whether a raw string passes the expected format.

        Args:
            raw:       The captured text value.
            validator: "amount", "date", "name", or "id".

        Returns:
            True if the format is valid.
        """
        if validator == "amount":
            return parse_amount(raw) is not None
        if validator == "date":
            return parse_date(raw) is not None
        if validator == "name":
            # Name: only letters, spaces, and common punctuation (dots, hyphens)
            return bool(re.match(r"^[A-Za-z][A-Za-z\s.\-']{1,}$", raw))
        if validator == "id":
            # ID: letters, digits, hyphens (e.g. LA-2026-0001, POL-2025-5501)
            return bool(re.match(r"^[A-Za-z0-9\-]+$", raw.strip()))
        return False

    def _find_source_line(self, text: str, value: str) -> str:
        """Return the full line from text that contains the given value.

        Used to populate source_text in ExtractedField for traceability.

        Args:
            text:  Full document text.
            value: Substring to search for.

        Returns:
            The matching line, or the value itself if not found.
        """
        for line in text.splitlines():
            if value in line:
                return line.strip()
        return value
