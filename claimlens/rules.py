"""
claimlens/rules.py
Business rule definitions and the DecisionEngine for ClaimLens AI.
No ML -- all decisions are transparent, rule-based recommendations.
"""

import abc

from claimlens.models import ExtractedField, Finding, Decision
from claimlens.extraction import parse_amount


# ---------------------------------------------------------------------------
# CONFIG -- tune thresholds here without touching rule logic
# ---------------------------------------------------------------------------

CONFIG: dict[str, float | int] = {
    "ratio_limit": 10,          # loan must not exceed income x this factor
    "large_loan": 2_000_000,    # flag loans above this value (Rs.)
    "large_claim": 500_000,     # flag claims above this value (Rs.)
    "low_confidence": 0.9,      # fields below this score get a LOW_CONFIDENCE flag
}


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------

class Rule(abc.ABC):
    """Abstract base for all business rules."""

    @abc.abstractmethod
    def evaluate(self, fields: dict[str, ExtractedField]) -> list[Finding]:
        """Evaluate this rule against the extracted fields.

        Args:
            fields: Dict mapping field key -> ExtractedField.

        Returns:
            List of Finding objects raised by this rule.
        """


# ---------------------------------------------------------------------------
# Concrete rule subclasses
# ---------------------------------------------------------------------------

class MissingCriticalFieldRule(Rule):
    """Raise MISSING_CRITICAL_FIELD (high) when a mandatory field is absent.

    Critical fields differ by document type:
      - Loan: applicant_name, monthly_income, loan_amount
      - Claim: applicant_name, policy_number, claim_amount
    """

    # Fields required for each document type
    CRITICAL_FIELDS: dict[str, list[str]] = {
        "loan":  ["applicant_name", "monthly_income", "loan_amount"],
        "claim": ["applicant_name", "policy_number", "claim_amount"],
    }

    def evaluate(self, fields: dict[str, ExtractedField]) -> list[Finding]:
        findings: list[Finding] = []

        # Determine doc type from which critical fields are present in the dict
        doc_type = self._detect_doc_type(fields)
        critical = self.CRITICAL_FIELDS.get(doc_type, [])

        for key in critical:
            ef = fields.get(key)
            # Missing if the field was never extracted, or has no value
            if ef is None or ef.status == "missing" or ef.value is None:
                findings.append(Finding(
                    code="MISSING_CRITICAL_FIELD",
                    severity="high",
                    message=(
                        f"Critical field '{key}' is missing from the document. "
                        f"This field is required to process this application."
                    ),
                ))
        return findings

    def _detect_doc_type(self, fields: dict[str, ExtractedField]) -> str:
        """Infer loan vs claim from which field keys exist."""
        if "loan_amount" in fields or "monthly_income" in fields:
            return "loan"
        if "claim_amount" in fields or "policy_number" in fields:
            return "claim"
        return "unknown"


class IncomeToLoanRatioRule(Rule):
    """Raise HIGH_LOAN_TO_INCOME (high) when the loan exceeds ratio_limit x income."""

    def evaluate(self, fields: dict[str, ExtractedField]) -> list[Finding]:
        findings: list[Finding] = []
        income_ef = fields.get("monthly_income")
        loan_ef = fields.get("loan_amount")

        # Skip if either field is missing
        if income_ef is None or loan_ef is None:
            return findings
        if income_ef.value is None or loan_ef.value is None:
            return findings

        income = parse_amount(income_ef.value)
        loan = parse_amount(loan_ef.value)

        # Skip if parsing failed or income is zero (avoid division by zero)
        if income is None or loan is None or income <= 0:
            return findings

        ratio = loan / income
        limit = CONFIG["ratio_limit"]

        if ratio > limit:
            findings.append(Finding(
                code="HIGH_LOAN_TO_INCOME",
                severity="high",
                message=(
                    f"Loan amount (Rs. {loan:,.0f}) is {ratio:.1f}x the monthly income "
                    f"(Rs. {income:,.0f}), which exceeds the allowed limit of {limit}x."
                ),
            ))
        return findings


class UnusuallyLargeAmountRule(Rule):
    """Raise LARGE_AMOUNT (medium) when a loan or claim amount is unusually large."""

    def evaluate(self, fields: dict[str, ExtractedField]) -> list[Finding]:
        findings: list[Finding] = []

        # Check loan amount
        loan_ef = fields.get("loan_amount")
        if loan_ef is not None and loan_ef.value is not None:
            amount = parse_amount(loan_ef.value)
            limit = CONFIG["large_loan"]
            if amount is not None and amount > limit:
                findings.append(Finding(
                    code="LARGE_AMOUNT",
                    severity="medium",
                    message=(
                        f"Loan amount Rs. {amount:,.0f} exceeds the large-loan "
                        f"threshold of Rs. {limit:,.0f}."
                    ),
                ))

        # Check claim amount
        claim_ef = fields.get("claim_amount")
        if claim_ef is not None and claim_ef.value is not None:
            amount = parse_amount(claim_ef.value)
            limit = CONFIG["large_claim"]
            if amount is not None and amount > limit:
                findings.append(Finding(
                    code="LARGE_AMOUNT",
                    severity="medium",
                    message=(
                        f"Claim amount Rs. {amount:,.0f} exceeds the large-claim "
                        f"threshold of Rs. {limit:,.0f}."
                    ),
                ))

        return findings


class LowConfidenceFieldRule(Rule):
    """Raise LOW_CONFIDENCE (low) for any field with confidence in (0, low_confidence)."""

    def evaluate(self, fields: dict[str, ExtractedField]) -> list[Finding]:
        findings: list[Finding] = []
        threshold = CONFIG["low_confidence"]

        for key, ef in fields.items():
            # Only flag fields that were actually found (confidence > 0)
            if 0 < ef.confidence < threshold:
                findings.append(Finding(
                    code="LOW_CONFIDENCE",
                    severity="low",
                    message=(
                        f"Field '{key}' was extracted with low confidence "
                        f"({ef.confidence:.2f}). Manual verification recommended."
                    ),
                ))
        return findings


# ---------------------------------------------------------------------------
# DecisionEngine
# ---------------------------------------------------------------------------

class DecisionEngine:
    """Runs all rules, merges findings, and produces a final Decision.

    Recommendation logic (in priority order):
      1. Any high finding whose code is NOT MISSING_CRITICAL_FIELD
         -> "Recommend: Escalate for investigation"
      2. MISSING_CRITICAL_FIELD present OR any medium finding
         -> "Recommend: Needs additional information"
      3. Otherwise
         -> "Recommend: Proceed to review"
    """

    # All registered rules, evaluated in order
    RULES: list[Rule] = [
        MissingCriticalFieldRule(),
        IncomeToLoanRatioRule(),
        UnusuallyLargeAmountRule(),
        LowConfidenceFieldRule(),
    ]

    def decide(
        self,
        fields: dict[str, ExtractedField],
        validation_findings: list[Finding],
    ) -> Decision:
        """Run all rules, merge findings, and return a Decision.

        Args:
            fields:               Extracted fields from the document.
            validation_findings:  Findings already raised by the Validator.

        Returns:
            A Decision with recommendation, reasons, and risk_indicators.
        """
        # Collect rule-based findings
        rule_findings: list[Finding] = []
        for rule in self.RULES:
            rule_findings.extend(rule.evaluate(fields))

        # Merge all findings (validation first, then rules)
        all_findings = validation_findings + rule_findings

        # Determine recommendation
        recommendation = self._pick_recommendation(all_findings)

        # Build plain-English reasons
        reasons = self._build_reasons(recommendation, all_findings)

        return Decision(
            recommendation=recommendation,
            reasons=reasons,
            risk_indicators=all_findings,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _pick_recommendation(self, findings: list[Finding]) -> str:
        """Apply the three-tier recommendation logic."""
        codes = {f.code for f in findings}
        severities = {f.severity for f in findings}

        # Tier 1: high finding that is NOT missing-critical-field
        high_non_missing = any(
            f.severity == "high" and f.code != "MISSING_CRITICAL_FIELD"
            for f in findings
        )
        if high_non_missing:
            return "Recommend: Escalate for investigation"

        # Tier 2: missing critical field OR any medium finding
        if "MISSING_CRITICAL_FIELD" in codes or "medium" in severities:
            return "Recommend: Needs additional information"

        # Tier 3: clean
        return "Recommend: Proceed to review"

    def _build_reasons(self, recommendation: str, findings: list[Finding]) -> list[str]:
        """Build a list of reasons: summary line first, then one per finding."""
        reasons: list[str] = [recommendation]

        for f in findings:
            # One sentence per finding: name the rule code and the values
            reasons.append(f"[{f.code} / {f.severity}] {f.message}")

        return reasons
