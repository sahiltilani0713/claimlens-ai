"""
ui/pages.py
Streamlit page renderers for ClaimLens AI.
Each function receives the shared CaseService from session_state.
"""

import pandas as pd
import streamlit as st

from claimlens.services import CaseService


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _rec_badge(rec: str) -> str:
    """Return an HTML-coloured badge for a recommendation string."""
    colours = {
        "PROCEED": ("#22c55e", "#052e16"),          # green
        "NEEDS_INFO": ("#f59e0b", "#1c1008"),        # amber
        "ESCALATE": ("#ef4444", "#1f0707"),          # red
    }
    bg, fg = colours.get(rec.upper(), ("#64748b", "#f8fafc"))
    return (
        f'<span style="background:{bg};color:{fg};padding:2px 10px;'
        f'border-radius:12px;font-size:0.8rem;font-weight:700;">'
        f"{rec}</span>"
    )


# ---------------------------------------------------------------------------
# Upload page
# ---------------------------------------------------------------------------

def render_upload(service: CaseService) -> None:
    """Render the Upload page: file uploader + Analyze button.

    Args:
        service: The shared CaseService instance.
    """
    st.subheader("📤 Upload Documents")
    st.write("Upload one or more PDF loan applications or insurance claims for analysis.")

    uploaded_files = st.file_uploader(
        "Select PDF files",
        type=["pdf"],
        accept_multiple_files=True,
        key="upload_files",
    )

    if st.button("🔍 Analyze", type="primary", disabled=not uploaded_files):
        results = []
        progress = st.progress(0, text="Analyzing…")
        total = len(uploaded_files)

        for i, uf in enumerate(uploaded_files):
            try:
                case_id = service.process_upload(uf.name, uf.read())
                from claimlens.repository import CaseRepository
                # Fetch the recommendation from the case just created
                case = service.repo.get_case(case_id)
                rec = case.decision.recommendation if (case and case.decision) else "—"
                results.append({"Filename": uf.name, "Recommendation": rec})
            except Exception as exc:
                results.append({"Filename": uf.name, "Recommendation": f"Error: {exc}"})
            progress.progress((i + 1) / total, text=f"Processed {i + 1}/{total}")

        progress.empty()
        st.success(f"✅ Analyzed {len(results)} file(s).")

        # Small summary table
        df = pd.DataFrame(results)
        st.dataframe(df, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Cases page
# ---------------------------------------------------------------------------

def render_cases(service: CaseService) -> None:
    """Render the Cases list page with metrics, filters and a table.

    Args:
        service: The shared CaseService instance.
    """
    st.subheader("📋 All Cases")

    # ---- Fetch all cases for metrics ----
    try:
        all_cases = service.repo.list_cases()
    except Exception as exc:
        st.error(f"Could not load cases: {exc}")
        return

    total = len(all_cases)
    escalate_count = sum(
        1 for c in all_cases
        if c.decision and "ESCALATE" in c.decision.recommendation.upper()
    )
    needs_info_count = sum(
        1 for c in all_cases
        if c.decision and "NEEDS ADDITIONAL" in c.decision.recommendation.upper()
    )
    proceed_count = sum(
        1 for c in all_cases
        if c.decision and "PROCEED" in c.decision.recommendation.upper()
    )

    # ---- Metric cards ----
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Cases", total)
    col2.metric("🔴 Escalate", escalate_count)
    col3.metric("🟡 Needs Info", needs_info_count)
    col4.metric("🟢 Proceed", proceed_count)

    st.divider()

    # ---- Filters ----
    f1, f2, f3 = st.columns([3, 2, 2])
    with f1:
        search = st.text_input("🔎 Search (filename or applicant)", key="cases_search")
    with f2:
        status_opts = ["", "auto_analyzed", "reviewed", "overridden"]
        status_filter = st.selectbox("Status", status_opts, key="cases_status")
    with f3:
        rec_opts = ["", "PROCEED", "NEEDS_INFO", "ESCALATE"]
        rec_filter = st.selectbox("Recommendation", rec_opts, key="cases_rec")

    # ---- Filtered fetch ----
    try:
        cases = service.repo.list_cases(
            search=search,
            status=status_filter,
            recommendation=rec_filter,
        )
    except Exception as exc:
        st.error(f"Filter error: {exc}")
        return

    if not cases:
        st.info("No cases match your filters.")
        return

    # ---- Build table rows ----
    rows = []
    for c in cases:
        rec = c.decision.recommendation if c.decision else "—"
        rows.append({
            "ID": c.case_id,
            "Filename": c.filename,
            "Doc Type": c.doc_type,
            "Recommendation": rec,
            "Status": c.status,
            "Created At": c.created_at,
        })

    df = pd.DataFrame(rows)

    # Colour-code Recommendation column via Styler
    def colour_rec(val: str) -> str:
        mapping = {
            "PROCEED": "color:#22c55e;font-weight:700",
            "NEEDS_INFO": "color:#f59e0b;font-weight:700",
            "ESCALATE": "color:#ef4444;font-weight:700",
        }
        return mapping.get(val.upper(), "")

    styled = df.style.map(colour_rec, subset=["Recommendation"])
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # ---- Open case selector ----
    st.divider()
    case_ids = [c.case_id for c in cases]
    chosen = st.selectbox(
        "Open case →",
        options=case_ids,
        format_func=lambda cid: f"Case #{cid} — {next((c.filename for c in cases if c.case_id == cid), '')}",
        key="cases_open_select",
    )
    if st.button("Open in Case Detail", key="cases_open_btn"):
        st.session_state["selected_case_id"] = chosen
        st.info("✅ Case selected. Switch to **Case Detail** in the sidebar.")


# ---------------------------------------------------------------------------
# Case Detail page
# ---------------------------------------------------------------------------

def render_case_detail(service: CaseService) -> None:
    """Render the Case Detail page (placeholder for now).

    Args:
        service: The shared CaseService instance.
    """
    st.subheader("🔍 Case Detail")
    st.info("Coming next — full case breakdown, field editor, and audit log.")
