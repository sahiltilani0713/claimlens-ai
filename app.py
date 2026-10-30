"""
app.py
ClaimLens AI — main Streamlit entry point.
Run with:  streamlit run app.py
"""

import streamlit as st

from claimlens.repository import CaseRepository
from claimlens.services import CaseService
from ui.pages import render_case_detail, render_cases, render_upload

# ---------------------------------------------------------------------------
# Page config (must be first Streamlit call)
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="ClaimLens AI",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------

st.markdown(
    """
    <style>
    /* ── Global ── */
    html, body, [class*="css"] {
        font-family: 'Inter', 'Segoe UI', sans-serif;
    }

    /* ── Page header / section titles ── */
    h1, h2, h3 {
        color: #93c5fd !important;
        font-weight: 700;
    }

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1e3a5f 0%, #2d5986 100%);
    }
    section[data-testid="stSidebar"] * {
        color: #e8f0fe !important;
    }
    section[data-testid="stSidebar"] .stRadio label {
        font-size: 1rem;
    }

    /* ── Metric cards ── */
    [data-testid="metric-container"] {
        background: #f0f6ff;
        border: 1px solid #bfd4f0;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 2px 8px rgba(30,58,95,0.08);
    }
    [data-testid="stMetricValue"] {
        color: #1e3a5f !important;
        font-size: 2rem !important;
        font-weight: 800 !important;
    }
    [data-testid="stMetricLabel"] {
        color: #4a6fa5 !important;
        font-weight: 600;
    }

    /* ── Buttons ── */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #1e3a5f, #2d5986);
        color: #fff;
        border: none;
        border-radius: 8px;
        font-weight: 700;
        padding: 0.5rem 1.5rem;
        transition: opacity 0.2s;
    }
    .stButton > button[kind="primary"]:hover {
        opacity: 0.88;
    }

    /* ── Info banner ── */
    [data-testid="stAlert"] {
        border-radius: 8px;
    }

    /* ── Colour-coded recommendation text ── */
    .rec-proceed  { color: #16a34a; font-weight: 700; }
    .rec-needsinfo{ color: #d97706; font-weight: 700; }
    .rec-escalate { color: #dc2626; font-weight: 700; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session-state singletons
# ---------------------------------------------------------------------------

if "repo" not in st.session_state:
    st.session_state["repo"] = CaseRepository("data/claimlens.db")

if "service" not in st.session_state:
    st.session_state["service"] = CaseService(st.session_state["repo"])

if "selected_case_id" not in st.session_state:
    st.session_state["selected_case_id"] = None

service: CaseService = st.session_state["service"]

# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("## 🔎 ClaimLens AI")
    st.markdown("---")
    page = st.radio(
        "Navigate",
        options=["Upload", "Cases", "Case Detail"],
        key="nav_page",
    )
    st.markdown("---")
    st.caption("v0.5 · Synthetic data only")

# ---------------------------------------------------------------------------
# Persistent disclaimer banner
# ---------------------------------------------------------------------------

st.info(
    "⚠️ **Recommendations only, for human review.** "
    "ClaimLens AI never approves or rejects applications automatically. "
    "All documents are synthetic.",
    icon="ℹ️",
)

# ---------------------------------------------------------------------------
# Route to page
# ---------------------------------------------------------------------------

if page == "Upload":
    render_upload(service)
elif page == "Cases":
    render_cases(service)
elif page == "Case Detail":
    render_case_detail(service)
