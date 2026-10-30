"""
claimlens/services.py
High-level service layer that orchestrates upload, analysis, correction, and override.
"""

import re
import tempfile
from datetime import datetime
from pathlib import Path

from claimlens.extraction import PDFExtractor, parse_amount, parse_date
from claimlens.models import Case
from claimlens.repository import CaseRepository
from claimlens.rules import DecisionEngine
from claimlens.validation import Validator


class CaseService:
    """Orchestrates the full ClaimLens workflow using a CaseRepository.

    Args:
        repository: A CaseRepository instance for persistence.
    """

    def __init__(self, repository: CaseRepository) -> None:
        self.repo = repository
        self._extractor = PDFExtractor()
        self._validator = Validator()
        self._engine = DecisionEngine()

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def process_upload(self, filename: str, file_bytes: bytes) -> int:
        """Write bytes to a temp file, run the full pipeline, and persist the case.

        Runs PDFExtractor -> Validator -> DecisionEngine, saves the case with
        status "auto_analyzed", and adds "uploaded" and "auto_analyzed" audit entries.

        Args:
            filename:   Original PDF filename (used for display / search).
            file_bytes: Raw bytes of the PDF.

        Returns:
            The new case_id integer.
        """
        # Write to a temporary file so pdfplumber can open it
        suffix = Path(filename).suffix or ".pdf"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            # Extract text and fields
            text = self._extractor.extract_text(tmp_path)
            doc_type = self._extractor.detect_doc_type(text)
            fields = self._extractor.extract_fields(text)

            # Validate and decide
            val_findings = self._validator.validate(fields)
            decision = self._engine.decide(fields, val_findings)

            # Build a Case dataclass (case_id is None until persisted)
            case = Case(
                case_id=None,
                filename=filename,
                doc_type=doc_type,
                fields=fields,
                findings=decision.risk_indicators,
                decision=decision,
                status="auto_analyzed",
                created_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
            )

            # Persist and capture the new ID
            case_id = self.repo.create_case(case)

        finally:
            # Always clean up the temp file
            Path(tmp_path).unlink(missing_ok=True)

        # Audit trail
        self.repo.add_audit(case_id, "system", "uploaded", f"File: {filename}")
        self.repo.add_audit(case_id, "system", "auto_analyzed",
                            f"Recommendation: {decision.recommendation}")

        return case_id

    def correct_field(
        self,
        case_id: int,
        field_name: str,
        new_value: str,
        reviewer: str,
    ) -> None:
        """Correct one field, re-run analysis, and persist the updated decision.

        Steps:
          1. Validate format of the new value (raise ValueError if invalid).
          2. Update the field value in the database.
          3. Reload the full case.
          4. Re-run Validator and DecisionEngine on all fields.
          5. Save the new decision.
          6. Set case status to "reviewed".
          7. Add an "decision_recomputed" audit entry.

        Args:
            case_id:    Target case ID.
            field_name: Name of the field to correct (e.g. "monthly_income").
            new_value:  Corrected string value.
            reviewer:   Name/ID of the human reviewer.

        Raises:
            ValueError: If the field value fails format validation or case not found.
        """
        # Step 1: validate format before saving anything
        self._validate_field(field_name, new_value)

        # Step 2: persist the corrected field (also writes a field_corrected audit entry)
        self.repo.update_field(case_id, field_name, new_value, reviewer)

        # Step 3: reload the updated case
        case = self.repo.get_case(case_id)
        if case is None:
            raise ValueError(f"Case {case_id} not found.")

        # Step 4: re-run validation and decision engine
        val_findings = self._validator.validate(case.fields)
        new_decision = self._engine.decide(case.fields, val_findings)

        # Step 5: replace findings and recommendation in the DB
        self.repo.save_decision(case_id, new_decision)

        # Step 6: set status to "reviewed"
        self._set_status(case_id, "reviewed")

        # Step 7: audit entry
        self.repo.add_audit(
            case_id,
            reviewer,
            "decision_recomputed",
            f"New recommendation: {new_decision.recommendation}",
        )

    def override_decision(
        self,
        case_id: int,
        new_recommendation: str,
        reason: str,
        reviewer: str,
    ) -> None:
        """Apply a manual override to a case recommendation.

        Delegates to repository.record_override which also writes the audit entry.

        Args:
            case_id:            Target case ID.
            new_recommendation: Override recommendation string.
            reason:             Mandatory reason for the override.
            reviewer:           Name/ID of the reviewer.

        Raises:
            ValueError: If reason is empty (raised by the repository).
        """
        self.repo.record_override(case_id, new_recommendation, reason, reviewer)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _set_status(self, case_id: int, status: str) -> None:
        """Update the status column of a case directly via SQL."""
        import sqlite3

        conn = sqlite3.connect(self.repo.db_path)
        try:
            conn.execute(
                "UPDATE cases SET status = ? WHERE id = ?",
                (status, case_id),
            )
            conn.commit()
        finally:
            conn.close()

    def _validate_field(self, field_name: str, value: str) -> None:
        """Validate field value using format checks before persisting.

        Rules:
          - name: letters and spaces only
          - IDs: letters, digits, and hyphens
          - amounts: parseable by parse_amount and > 0
          - dates: parseable by parse_date as DD-MM-YYYY

        Raises:
            ValueError: If the format check fails.
        """
        field_validators: dict[str, str] = {
            "applicant_name": "name",
            "application_id": "id",
            "policy_number": "id",
            "monthly_income": "amount",
            "loan_amount": "amount",
            "claim_amount": "amount",
            "application_date": "date",
            "loan_start_date": "date",
            "loan_end_date": "date",
            "policy_start_date": "date",
            "incident_date": "date",
        }
        validator = field_validators.get(field_name)
        if not validator:
            return

        val = value.strip() if value else ""

        if validator == "name":
            if not val or not re.match(r"^[A-Za-z\s]+$", val):
                raise ValueError("Applicant name must contain only letters and spaces.")

        elif validator == "id":
            if not val or not re.match(r"^[A-Za-z0-9\-]+$", val):
                label = "Application ID" if field_name == "application_id" else "Policy number"
                raise ValueError(f"{label} must contain only letters, digits, and hyphens.")

        elif validator == "amount":
            amt = parse_amount(val) if val else None
            if amt is None or amt <= 0:
                label = field_name.replace("_", " ").capitalize()
                raise ValueError(f"{label} must be a valid amount greater than 0.")

        elif validator == "date":
            if not val or not re.fullmatch(r"\d{2}-\d{2}-\d{4}", val) or parse_date(val) is None:
                label = field_name.replace("_", " ").capitalize()
                raise ValueError(f"{label} must be a valid date in DD-MM-YYYY format.")

