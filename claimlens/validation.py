"""
claimlens/validation.py
Validates extracted fields against business rules and returns Findings.
No ML -- pure rule-based checks.
"""

import datetime

from claimlens.models import ExtractedField, Finding
from claimlens.extraction import parse_amount, parse_date


class Validator:
    """Runs field-level validation checks and returns a list of Findings.

    Each check is skipped silently if the required field is missing
    or its value is None, so partial documents are handled gracefully.
    """

    def validate(self, fields: dict[str, ExtractedField]) -> list[Finding]:
        """Run all validation checks on the extracted fields.

        Args:
            fields: Dict mapping field key -> ExtractedField.

        Returns:
            List of Finding objects (may be empty if all checks pass).
        """
        findings: list[Finding] = []

        findings.extend(self._check_invalid_values(fields))
        findings.extend(self._check_negative_amounts(fields))
        findings.extend(self._check_future_dates(fields))
        findings.extend(self._check_date_order(fields))
        findings.extend(self._check_incident_before_policy(fields))

        return findings

    # ------------------------------------------------------------------
    # Private check methods
    # ------------------------------------------------------------------

    def _check_invalid_values(self, fields: dict[str, ExtractedField]) -> list[Finding]:
        """INVALID_VALUE (medium): field has status 'needs_review' and confidence == 0.4."""
        findings: list[Finding] = []
        for key, ef in fields.items():
            if ef.value is None:
                continue  # missing fields handled elsewhere
            if ef.status == "needs_review" and ef.confidence == 0.4:
                findings.append(Finding(
                    code="INVALID_VALUE",
                    severity="medium",
                    message=(
                        f"Field '{key}' has an invalid format. "
                        f"Extracted value: '{ef.value}'."
                    ),
                ))
        return findings

    def _check_negative_amounts(self, fields: dict[str, ExtractedField]) -> list[Finding]:
        """NEGATIVE_AMOUNT (high): any amount field parses to a value <= 0."""
        findings: list[Finding] = []
        amount_keys = [k for k in fields if "amount" in k or "income" in k]
        for key in amount_keys:
            ef = fields[key]
            if ef.value is None:
                continue
            amount = parse_amount(ef.value)
            if amount is not None and amount <= 0:
                findings.append(Finding(
                    code="NEGATIVE_AMOUNT",
                    severity="high",
                    message=(
                        f"Field '{key}' has a non-positive amount: {amount}. "
                        f"Amounts must be greater than zero."
                    ),
                ))
        return findings

    def _check_future_dates(self, fields: dict[str, ExtractedField]) -> list[Finding]:
        """FUTURE_DATE (medium): application_date or incident_date is later than today."""
        findings: list[Finding] = []
        today = datetime.date.today()
        date_keys = ["application_date", "incident_date"]
        for key in date_keys:
            ef = fields.get(key)
            if ef is None or ef.value is None:
                continue
            parsed = parse_date(ef.value)
            if parsed is not None and parsed > today:
                findings.append(Finding(
                    code="FUTURE_DATE",
                    severity="medium",
                    message=(
                        f"Field '{key}' has a future date: {parsed.strftime('%d-%m-%Y')} "
                        f"(today is {today.strftime('%d-%m-%Y')})."
                    ),
                ))
        return findings

    def _check_date_order(self, fields: dict[str, ExtractedField]) -> list[Finding]:
        """DATE_ORDER (high): loan_end_date is earlier than loan_start_date."""
        findings: list[Finding] = []
        start_ef = fields.get("loan_start_date")
        end_ef = fields.get("loan_end_date")
        if start_ef is None or end_ef is None:
            return findings
        if start_ef.value is None or end_ef.value is None:
            return findings
        start = parse_date(start_ef.value)
        end = parse_date(end_ef.value)
        if start is not None and end is not None and end < start:
            findings.append(Finding(
                code="DATE_ORDER",
                severity="high",
                message=(
                    f"Loan end date ({end.strftime('%d-%m-%Y')}) is earlier than "
                    f"loan start date ({start.strftime('%d-%m-%Y')}). "
                    f"This is chronologically impossible."
                ),
            ))
        return findings

    def _check_incident_before_policy(self, fields: dict[str, ExtractedField]) -> list[Finding]:
        """INCIDENT_BEFORE_POLICY (high): incident_date is earlier than policy_start_date."""
        findings: list[Finding] = []
        incident_ef = fields.get("incident_date")
        policy_ef = fields.get("policy_start_date")
        if incident_ef is None or policy_ef is None:
            return findings
        if incident_ef.value is None or policy_ef.value is None:
            return findings
        incident = parse_date(incident_ef.value)
        policy_start = parse_date(policy_ef.value)
        if incident is not None and policy_start is not None and incident < policy_start:
            findings.append(Finding(
                code="INCIDENT_BEFORE_POLICY",
                severity="high",
                message=(
                    f"Incident date ({incident.strftime('%d-%m-%Y')}) is before "
                    f"policy start date ({policy_start.strftime('%d-%m-%Y')}). "
                    f"The policy was not active at the time of the incident."
                ),
            ))
        return findings
