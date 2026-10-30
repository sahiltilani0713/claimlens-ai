"""
claimlens/models.py
Core dataclasses that represent every object flowing through ClaimLens AI.
No ML — all fields, findings and decisions are rule-based.
"""

from dataclasses import dataclass, field
from typing import Literal


# ---------------------------------------------------------------------------
# ExtractedField
# ---------------------------------------------------------------------------

@dataclass
class ExtractedField:
    """A single field parsed from a document.

    Attributes:
        name: Label of the field (e.g. "Monthly Income").
        value: Raw text value found, or None when absent.
        confidence: 0.0 – 1.0 rule-confidence score.
        status: Parsing outcome – "verified", "needs_review", or "missing".
        source_text: The original line from the document for traceability.
    """

    name: str
    value: str | None
    confidence: float
    status: Literal["verified", "needs_review", "missing"]
    source_text: str


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    """A single risk or compliance flag raised during analysis.

    Attributes:
        code: Short machine-readable identifier (e.g. "HIGH_LOAN_RATIO").
        severity: Impact level – "low", "medium", or "high".
        message: Human-readable explanation shown in the review UI.
    """

    code: str
    severity: Literal["low", "medium", "high"]
    message: str


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------

@dataclass
class Decision:
    """Final recommendation produced by the rule engine.

    Attributes:
        recommendation: Short action string, e.g. "APPROVE", "REVIEW", "REJECT".
        reasons: Plain-language reasons supporting the recommendation.
        risk_indicators: Findings that influenced this decision.
    """

    recommendation: str
    reasons: list[str] = field(default_factory=list)
    risk_indicators: list[Finding] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Case
# ---------------------------------------------------------------------------

@dataclass
class Case:
    """Top-level container for one processed document.

    Attributes:
        case_id: Auto-assigned integer ID (None until persisted).
        filename: Source PDF filename.
        doc_type: "Loan Application" or "Insurance Claim".
        fields: Extracted fields keyed by their label.
        findings: All findings raised during analysis.
        decision: Rule-engine output (None until analysis runs).
        status: Workflow state, e.g. "pending", "analysed", "reviewed".
        created_at: ISO-8601 timestamp string of case creation.
    """

    case_id: int | None
    filename: str
    doc_type: str
    fields: dict[str, ExtractedField]
    findings: list[Finding]
    decision: Decision | None
    status: str
    created_at: str
