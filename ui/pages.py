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
        "PROCEED": ("#22c55e", "#052e16"),
        "NEEDS_INFO": ("#f59e0b", "#1c1008"),
        "ESCALATE": ("#ef4444", "#1f0707"),
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
                case = service.repo.get_case(case_id)
                rec = case.decision.recommendation if (case and case.decision) else "—"
                results.append({"Filename": uf.name, "Recommendation": rec})
            except Exception as exc:
                results.append({"Filename": uf.name, "Recommendation": f"Error: {exc}"})
            progress.progress((i + 1) / total, text=f"Processed {i + 1}/{total}")

        progress.empty()
        st.success(f"✅ Analyzed {len(results)} file(s).")
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

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Cases", total)
    col2.metric("🔴 Escalate", escalate_count)
    col3.metric("🟡 Needs Info", needs_info_count)
    col4.metric("🟢 Proceed", proceed_count)

    st.divider()

    f1, f2, f3 = st.columns([3, 2, 2])
    with f1:
        search = st.text_input("🔎 Search (filename or applicant)", key="cases_search")
    with f2:
        status_opts = ["", "auto_analyzed", "reviewed", "overridden"]
        status_filter = st.selectbox("Status", status_opts, key="cases_status")
    with f3:
        rec_opts = ["", "PROCEED", "NEEDS_INFO", "ESCALATE"]
        rec_filter = st.selectbox("Recommendation", rec_opts, key="cases_rec")

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

    def colour_rec(val: str) -> str:
        """Return CSS for colour-coded recommendation."""
        mapping = {
            "PROCEED": "color:#22c55e;font-weight:700",
            "NEEDS_INFO": "color:#f59e0b;font-weight:700",
            "ESCALATE": "color:#ef4444;font-weight:700",
        }
        return mapping.get(val.upper(), "")

    styled = df.style.map(colour_rec, subset=["Recommendation"])
    st.dataframe(styled, use_container_width=True, hide_index=True)

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
    """Render the full Case Detail page.

    Displays a case selector (synced with session_state), a coloured header
    card with recommendation reasons, an extracted-fields table with confidence
    and status colour badges, validation findings grouped by severity, a
    field-correction st.form, a recommendation-override st.form (with an
    empty-reason guard), and a newest-first audit trail table.

    Args:
        service: The shared CaseService instance.
    """
    st.subheader("🔍 Case Detail")

    # ------------------------------------------------------------------
    # Case selector — allows picking a case directly on this page
    # ------------------------------------------------------------------
    try:
        all_cases = service.repo.list_cases()
    except Exception as exc:
        st.error(f"Could not load cases: {exc}")
        return

    if not all_cases:
        st.info("No cases found. Upload a document on the **Upload** page first.")
        return

    case_ids = [c.case_id for c in all_cases]
    current_id = st.session_state.get("selected_case_id")
    default_idx = case_ids.index(current_id) if current_id in case_ids else 0

    chosen_id = st.selectbox(
        "Select a case",
        options=case_ids,
        index=default_idx,
        format_func=lambda cid: (
            f"Case #{cid} — "
            f"{next((c.filename for c in all_cases if c.case_id == cid), '')}"
        ),
        key="detail_case_select",
    )
    st.session_state["selected_case_id"] = chosen_id

    if chosen_id is None:
        st.info("👈 Pick a case on the **Cases** page or use the selector above.")
        return

    # ------------------------------------------------------------------
    # Load the full case object
    # ------------------------------------------------------------------
    try:
        case = service.repo.get_case(chosen_id)
    except Exception as exc:
        st.error(f"Could not load case #{chosen_id}: {exc}")
        return

    if case is None:
        st.warning(f"Case #{chosen_id} was not found in the database.")
        return

    st.divider()

    # ------------------------------------------------------------------
    # 1. Header — filename, type, status + coloured recommendation card
    # ------------------------------------------------------------------
    rec = case.decision.recommendation if case.decision else "—"
    reasons = case.decision.reasons if case.decision else []

    rec_upper = rec.upper()
    if "PROCEED" in rec_upper:
        bg_col, border_col = "rgba(34,197,94,0.12)", "#22c55e"
    elif "NEEDS" in rec_upper:
        bg_col, border_col = "rgba(245,158,11,0.12)", "#f59e0b"
    elif "ESCALATE" in rec_upper:
        bg_col, border_col = "rgba(239,68,68,0.12)", "#ef4444"
    else:
        bg_col, border_col = "rgba(100,116,139,0.12)", "#64748b"

    h_col, rec_col = st.columns([3, 2])
    with h_col:
        st.markdown(f"**📄 File:** `{case.filename}`")
        st.markdown(f"**🗂 Type:** {case.doc_type}")
        st.markdown(f"**🔖 Status:** `{case.status}`")
        st.markdown(f"**🕒 Created:** {case.created_at}")

    with rec_col:
        reasons_html = (
            "".join(f"<li>{r}</li>" for r in reasons)
            if reasons
            else "<li>No reasons recorded.</li>"
        )
        st.markdown(
            f'<div style="background:{bg_col};border:2px solid {border_col};'
            f'border-radius:12px;padding:16px 20px;">'
            f'<div style="color:#f1f5f9;font-weight:700;font-size:1.1rem;margin-bottom:8px;">'
            f"Recommendation: {rec}"
            f'</div><ul style="margin:0;padding-left:18px;color:#f1f5f9;font-size:0.9rem;">'
            f"{reasons_html}</ul></div>",
            unsafe_allow_html=True,
        )

    st.divider()

    # ------------------------------------------------------------------
    # 2. Extracted fields table
    # ------------------------------------------------------------------
    st.markdown("### 📊 Extracted Fields")
    st.caption(
        "Confidence is a heuristic based on how the value was found and its "
        "format, not a statistical probability."
    )

    if case.fields:
        field_rows = [
            {
                "Name":       ef.name,
                "Value":      ef.value if ef.value is not None else "—",
                "Confidence": ef.confidence,
                "Status":     ef.status,
            }
            for ef in case.fields.values()
        ]
        fields_df = pd.DataFrame(field_rows)

        def _conf_style(val: float) -> str:
            """Green >=0.9, amber 0.4-0.89, red below 0.4."""
            if val >= 0.9:
                return "color:#16a34a;font-weight:700"
            if val >= 0.4:
                return "color:#d97706;font-weight:700"
            return "color:#dc2626;font-weight:700"

        def _status_style(val: str) -> str:
            """Colour by field status."""
            mapping = {
                "verified":     "color:#16a34a;font-weight:700",
                "needs_review": "color:#d97706;font-weight:700",
                "missing":      "color:#dc2626;font-weight:700",
            }
            return mapping.get(val.lower(), "")

        styled_fields = (
            fields_df.style
            .map(_conf_style, subset=["Confidence"])
            .map(_status_style, subset=["Status"])
            .format({"Confidence": "{:.0%}"})
        )
        st.dataframe(styled_fields, use_container_width=True, hide_index=True)
    else:
        st.info("No fields were extracted for this case.")

    st.divider()

    # ------------------------------------------------------------------
    # 3. Validation findings grouped by severity
    # ------------------------------------------------------------------
    st.markdown("### ⚠️ Validation Findings")

    findings = case.findings or []
    if not findings:
        st.success("No findings — all validation checks passed.")
    else:
        severity_groups = [
            ("high",   "🔴 High",   "#fee2e2", "#7f1d1d"),
            ("medium", "🟡 Medium", "#fef9c3", "#78350f"),
            ("low",    "🔵 Low",    "#dbeafe", "#1e3a5f"),
        ]
        for sev_key, sev_label, sev_bg, sev_fg in severity_groups:
            group = [f for f in findings if f.severity.lower() == sev_key]
            if not group:
                continue
            st.markdown(
                f'<div style="background:{sev_bg};border-radius:8px;'
                f'padding:8px 16px;margin-bottom:4px;">'
                f'<strong style="color:{sev_fg};">{sev_label}</strong></div>',
                unsafe_allow_html=True,
            )
            for finding in group:
                st.markdown(
                    f'<div style="margin-left:16px;padding:3px 0;color:{sev_fg};">'
                    f'• <code>{finding.code}</code> — {finding.message}</div>',
                    unsafe_allow_html=True,
                )

    st.divider()

    # ------------------------------------------------------------------
    # 4. Correct a field
    # ------------------------------------------------------------------
    st.markdown("### ✏️ Correct a Field")

    field_names = list(case.fields.keys()) if case.fields else []
    if not field_names:
        st.info("No fields available to correct.")
    else:
        with st.form("correct_field_form", clear_on_submit=True):
            selected_field = st.selectbox("Field to correct", options=field_names)
            new_value = st.text_input("New value")
            reviewer_name = st.text_input("Your name / reviewer ID")
            submitted = st.form_submit_button("💾 Submit Correction", type="primary")

        if submitted:
            try:
                service.correct_field(chosen_id, selected_field, new_value, reviewer_name)
                st.success(f"✅ Field **{selected_field}** corrected. Analysis recomputed.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Correction failed: {exc}")

    st.divider()

    # ------------------------------------------------------------------
    # 5. Override recommendation
    # ------------------------------------------------------------------
    st.markdown("### 🔄 Override Recommendation")

    rec_options = ["PROCEED", "NEEDS_INFO", "ESCALATE"]
    with st.form("override_form", clear_on_submit=True):
        new_rec = st.selectbox("New recommendation", options=rec_options)
        override_reason = st.text_area("Reason for override (required)")
        override_reviewer = st.text_input(
            "Your name / reviewer ID", key="override_reviewer_input"
        )
        override_submitted = st.form_submit_button("🔄 Submit Override", type="primary")

    if override_submitted:
        if not override_reason or not override_reason.strip():
            st.error("❌ A reason is required before submitting an override.")
        else:
            try:
                service.override_decision(
                    chosen_id, new_rec, override_reason, override_reviewer
                )
                st.success(f"✅ Recommendation overridden to **{new_rec}**.")
                st.rerun()
            except Exception as exc:
                st.error(f"Override failed: {exc}")

    st.divider()

    # ------------------------------------------------------------------
    # 6. Audit trail — newest first
    # ------------------------------------------------------------------
    st.markdown("### 📜 Audit Trail")

    try:
        audit_entries = service.repo.get_audit_log(chosen_id)
    except Exception as exc:
        st.error(f"Could not load audit log: {exc}")
        audit_entries = []

    if not audit_entries:
        st.info("No audit entries yet for this case.")
    else:
        audit_rows = [
            {
                "Time (UTC)": entry.get("timestamp", ""),
                "Actor":      entry.get("actor", ""),
                "Action":     entry.get("action", ""),
                "Details":    entry.get("details", ""),
            }
            for entry in audit_entries
        ]
        audit_df = pd.DataFrame(audit_rows)
        st.dataframe(audit_df, use_container_width=True, hide_index=True)
