"""
scripts/test_pipeline.py
End-to-end smoke test for the ClaimLens AI repository and service layer.

Usage:
    python -m scripts.test_pipeline
"""

import os
from pathlib import Path

from claimlens.repository import CaseRepository
from claimlens.services import CaseService

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DB_PATH = "data/test_claimlens.db"
SAMPLE_DIR = Path("sample_docs")

# ---------------------------------------------------------------------------
# Step 0 – delete stale test database
# ---------------------------------------------------------------------------

if Path(DB_PATH).exists():
    os.remove(DB_PATH)
    print(f"[setup] Deleted existing database: {DB_PATH}\n")

# ---------------------------------------------------------------------------
# Step 1 – initialise repository and service
# ---------------------------------------------------------------------------

repo = CaseRepository(db_path=DB_PATH)
service = CaseService(repository=repo)

# ---------------------------------------------------------------------------
# Step 2 – process every PDF in sample_docs/
# ---------------------------------------------------------------------------

pdf_files = sorted(SAMPLE_DIR.glob("*.pdf"))
case_ids: dict[str, int] = {}   # filename stem -> case_id

print("=" * 60)
print("PROCESSING ALL SAMPLE PDFs")
print("=" * 60)

for pdf_path in pdf_files:
    file_bytes = pdf_path.read_bytes()
    case_id = service.process_upload(pdf_path.name, file_bytes)
    case_ids[pdf_path.stem] = case_id

    case = repo.get_case(case_id)
    recommendation = case.decision.recommendation if case and case.decision else "N/A"

    print(f"\n[{pdf_path.name}]  case_id={case_id}")
    print(f"  Recommendation : {recommendation}")
    if case and case.decision:
        for reason in case.decision.reasons[1:]:   # skip the leading summary line
            print(f"    * {reason}")

# ---------------------------------------------------------------------------
# Step 3 – correct loan_02 missing monthly_income and print new recommendation
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
print("CORRECTING loan_02 monthly_income -> 'Rs. 50,000'")
print("=" * 60)

loan02_id = case_ids["loan_02_missing_income"]
service.correct_field(
    case_id=loan02_id,
    field_name="monthly_income",
    new_value="Rs. 50,000",
    reviewer="test_reviewer",
)

case = repo.get_case(loan02_id)
recommendation = case.decision.recommendation if case and case.decision else "N/A"
print(f"\n[loan_02]  new recommendation: {recommendation}")
if case and case.decision:
    for reason in case.decision.reasons[1:]:
        print(f"    * {reason}")

# ---------------------------------------------------------------------------
# Step 4 – override loan_03 with a reason
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
print("OVERRIDING loan_03 decision")
print("=" * 60)

loan03_id = case_ids["loan_03_high_ratio"]
service.override_decision(
    case_id=loan03_id,
    new_recommendation="Recommend: Proceed to review",
    reason="Applicant has provided additional collateral; escalation waived.",
    reviewer="senior_reviewer",
)

case = repo.get_case(loan03_id)
print(f"\n[loan_03]  overridden recommendation: {case.decision.recommendation if case and case.decision else 'N/A'}")
print(f"           status: {case.status if case else 'N/A'}")

# ---------------------------------------------------------------------------
# Step 5 – verify that an empty reason raises ValueError
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
print("TESTING: empty reason raises ValueError")
print("=" * 60)

try:
    service.override_decision(
        case_id=loan03_id,
        new_recommendation="Recommend: Reject",
        reason="",
        reviewer="bad_actor",
    )
    print("  ERROR: ValueError was NOT raised -- this is a bug!")
except ValueError as exc:
    print(f'  OK: ValueError raised as expected -> "{exc}"')

# ---------------------------------------------------------------------------
# Step 6 – print audit logs for loan_02 and loan_03
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
print("AUDIT LOG -- loan_02")
print("=" * 60)

for entry in reversed(repo.get_audit_log(loan02_id)):   # show oldest first
    print(f"  [{entry['timestamp']}] actor={entry['actor']}  action={entry['action']}")
    if entry["details"]:
        print(f"    details: {entry['details']}")

print("\n" + "=" * 60)
print("AUDIT LOG -- loan_03")
print("=" * 60)

for entry in reversed(repo.get_audit_log(loan03_id)):
    print(f"  [{entry['timestamp']}] actor={entry['actor']}  action={entry['action']}")
    if entry["details"]:
        print(f"    details: {entry['details']}")

# ---------------------------------------------------------------------------
# Step 7 – total case count
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
all_cases = repo.list_cases()
print(f"TOTAL CASES IN DATABASE: {len(all_cases)}")
print("=" * 60)
