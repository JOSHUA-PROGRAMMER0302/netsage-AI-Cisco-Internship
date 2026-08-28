"""NetSage AI: Cisco troubleshooting, review, and quality analytics."""

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from diagnose import DiagnosisResponse, run_ai_diagnosis
from logger import ReviewLogger
from rule_checker import NetworkRuleChecker

ROOT = Path(__file__).parent
CASES_FILE = ROOT / "cases.csv"
REVIEWS_FILE = ROOT / "responsible_ai_log.json"

st.set_page_config(page_title="NetSage AI", page_icon="◈", layout="wide")


@st.cache_data(show_spinner=False)
def load_cases(path):
    return pd.read_csv(path)


@st.cache_data(show_spinner=False)
def load_reviews(path):
    review_path = Path(path)
    if not review_path.exists():
        return pd.DataFrame()
    try:
        value = json.loads(review_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return pd.DataFrame()
    return pd.DataFrame(value) if isinstance(value, list) else pd.DataFrame()


def apply_css():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Fira+Code:wght@400;500;600&family=Space+Grotesk:wght@500;600;700&display=swap');
        :root { --bg:#070f17; --slate:#0c1a25; --panel:#102532; --line:#203a49; --text:#e6f2f5; --muted:#8ca6b1; --cyan:#20d3d8; --cyan-dark:#0b8e9b; }
        .stApp { background:radial-gradient(circle at 88% -4%, #123a4a 0, transparent 30%), linear-gradient(145deg, var(--bg), #0b1721 72%, #071018); color:var(--text); }
        html, body, [class*="css"] { font-family:'DM Sans',sans-serif; }
        h1, h2, h3 { font-family:'Space Grotesk',sans-serif; letter-spacing:0; }
        h1 { font-size:2.4rem; }
        [data-testid="stSidebar"] { background:var(--slate); border-right:1px solid var(--line); }
        [data-testid="stSidebar"] * { color:var(--text); }
        [data-testid="stTextArea"] textarea { background:#07131d; border:1px solid var(--line); border-radius:6px; color:#b9f7f2; font-family:'Fira Code','Courier New',monospace; font-size:.86rem; line-height:1.55; }
        [data-testid="stTextArea"] textarea:focus { border-color:var(--cyan); box-shadow:0 0 0 1px var(--cyan); }
        .eyebrow { color:var(--cyan); font-size:.75rem; font-weight:700; letter-spacing:.13em; text-transform:uppercase; }
        .subtle { color:var(--muted); margin-bottom:1.2rem; }
        .metric { background:linear-gradient(140deg,#102b3a,#0d202c); border:1px solid var(--line); border-radius:8px; padding:1rem 1.1rem; min-height:86px; }
        .metric-label { color:var(--muted); font-size:.73rem; text-transform:uppercase; letter-spacing:.09em; }
        .metric-value { color:var(--text); font-family:'Space Grotesk'; font-size:1.35rem; font-weight:700; margin-top:.25rem; overflow-wrap:anywhere; }
        div.stButton > button, div.stFormSubmitButton > button { background:var(--cyan); color:#04131a; border:0; border-radius:6px; font-weight:700; }
        div.stButton > button:hover, div.stFormSubmitButton > button:hover { background:#66e0e5; color:#04131a; }
        #MainMenu { visibility:hidden; }
        footer { visibility:hidden; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def metric(label, value):
    st.markdown(f'<div class="metric"><div class="metric-label">{label}</div><div class="metric-value">{value}</div></div>', unsafe_allow_html=True)


def fault_type(text):
    lowered = text.lower()
    if "vlan" in lowered or "inter-vlan" in lowered:
        return "VLAN"
    if "dhcp" in lowered:
        return "DHCP"
    if "route" in lowered or "routing" in lowered:
        return "Routing"
    return "Other"


def diagnosis_tab(api_key):
    st.markdown('<div class="eyebrow">Operations / live signal analysis</div>', unsafe_allow_html=True)
    st.title("Live Troubleshooter")
    st.markdown('<div class="subtle">Validate network evidence first, then ask Gemini for a structured TAC assessment.</div>', unsafe_allow_html=True)
    symptom = st.text_area("Symptom", height=110, placeholder="VLAN 47 clients cannot reach the server subnet")
    show_output = st.text_area("Show Output", height=270, placeholder="Paste show ip interface brief, show ip route, or show access-lists output")
    if st.button("Run Diagnosis", type="primary"):
        if not symptom.strip() or not show_output.strip():
            st.warning("Enter both a symptom and show output.")
        elif not api_key:
            st.error("Enter GEMINI_API_KEY in the sidebar before running a diagnosis.")
        else:
            with st.status("Running deterministic network validation...", expanded=True) as validation_status:
                deterministic_errors = NetworkRuleChecker().check(
                    {"interface_brief": show_output, "interface_config": show_output, "route_output": show_output}
                )
                if deterministic_errors:
                    error_lines = []
                    for category, details in deterministic_errors.items():
                        if isinstance(details, dict):
                            detail_text = "; ".join(f"{key}: {value}" for key, value in details.items())
                            error_lines.append(f"- **{category}**: {detail_text}")
                        elif isinstance(details, list):
                            error_lines.extend(f"- **{category}**: {detail}" for detail in details)
                        else:
                            error_lines.append(f"- **{category}**: {details}")
                    st.error("Basic network checks found configuration errors:\n\n" + "\n".join(error_lines))
                    validation_status.update(
                        label="Deterministic validation found basic network errors.", state="error"
                    )
                else:
                    st.success("Basic syntax and Layer 1/2 checks passed.")
                    validation_status.update(label="Deterministic validation complete.", state="complete")
            try:
                st.session_state.diagnosis = run_ai_diagnosis(symptom, show_output, api_key)
                st.session_state.diagnosis_input = {"symptom": symptom, "show_output": show_output}
                st.session_state.review_saved = False
            except (RuntimeError, ValueError) as error:
                st.error(str(error))

    diagnosis = st.session_state.get("diagnosis")
    if diagnosis is None:
        st.info("A validated diagnosis will appear here after analysis.")
        return
    st.divider()
    st.subheader("Diagnosis")
    summary, confidence = st.columns([2.2, 1], gap="large")
    with summary:
        if diagnosis.confidence == "High":
            st.error(f"**Root Cause**\n\n{diagnosis.root_cause}")
        else:
            st.warning(f"**Root Cause**\n\n{diagnosis.root_cause}")
    with confidence:
        st.metric("Confidence", diagnosis.confidence)
    st.markdown("**Evidence**")
    st.code(diagnosis.evidence, language="text")
    with st.expander("View Recommended Remediation Steps"):
        st.markdown(f"**Next Command**\n\n```bash\n{diagnosis.next_command}\n```")
        st.markdown("**Fix Steps**")
        for index, step in enumerate(diagnosis.fix_steps, 1):
            st.markdown(f"{index}. {step}")
    st.divider()
    st.subheader("Human Review")
    with st.form("review_form"):
        st.subheader("TAC Engineer Validation")
        decision = st.radio("Decision", ["Accepted", "Edited", "Rejected"], horizontal=True)
        feedback = st.text_area("Human Feedback/Correction", height=100)
        submitted = st.form_submit_button("Submit Review")
        if submitted:
            context = st.session_state.get("diagnosis_input", {})
            ReviewLogger(str(REVIEWS_FILE)).append(
                decision,
                feedback,
                {"symptom": context.get("symptom", ""), "fault_type": fault_type(context.get("symptom", "")), "ai_confidence": diagnosis.confidence},
            )
            load_reviews.clear()
            st.toast("Review logged successfully to responsible_ai_log.json", icon="✅")


def dataset_tab():
    st.markdown('<div class="eyebrow">Reference / troubleshooting catalog</div>', unsafe_allow_html=True)
    st.title("Dataset Explorer")
    cases = load_cases(str(CASES_FILE))
    query = st.text_input("Search cases", placeholder="Search symptoms, faults, or topology notes")
    first, second = st.columns(2)
    with first:
        tags = st.multiselect("Concept Tag", sorted(cases["Concept Tag"].dropna().unique()))
    with second:
        layers = st.multiselect("OSI Layer", sorted(cases["OSI Layer"].dropna().unique()))
    filtered = cases
    if query:
        mask = filtered.astype(str).apply(lambda column: column.str.contains(query, case=False, na=False)).any(axis=1)
        filtered = filtered[mask]
    if tags:
        filtered = filtered[filtered["Concept Tag"].isin(tags)]
    if layers:
        filtered = filtered[filtered["OSI Layer"].isin(layers)]
    st.caption(f"Showing {len(filtered)} of {len(cases)} cases")
    st.dataframe(filtered, use_container_width=True, hide_index=True)


def analytics_tab():
    st.markdown('<div class="eyebrow">Governance / model quality</div>', unsafe_allow_html=True)
    st.title("Analytics Dashboard")
    reviews = load_reviews(str(REVIEWS_FILE))
    decisions = reviews.get("decision", pd.Series(dtype=str))
    total = len(reviews)
    accepted = int(decisions.eq("Accepted").sum())
    corrected = int(decisions.isin(["Edited", "Rejected"]).sum())
    cols = st.columns(3)
    with cols[0]: metric("Total Cases Diagnosed", total)
    with cols[1]: metric("Acceptance Rate", f"{accepted / total:.0%}" if total else "—")
    with cols[2]: metric("Correction Count", corrected)
    st.divider()
    st.subheader("Fault Types vs. Accuracy")
    if reviews.empty or "fault_type" not in reviews:
        st.info("Submit a human review to populate accuracy by fault type.")
    else:
        chart_data = reviews.assign(accepted=reviews["decision"].eq("Accepted")).groupby("fault_type")["accepted"].mean().mul(100).rename("Accuracy (%)").to_frame()
        st.bar_chart(chart_data, color="#19c3d1")
    st.subheader("Documented Human Corrections")
    if reviews.empty:
        st.info("No documented corrections yet.")
    else:
        notes = reviews["correction_notes"].fillna("").astype(str).str.strip() if "correction_notes" in reviews else pd.Series(False, index=reviews.index)
        st.dataframe(reviews[notes.ne("")], use_container_width=True, hide_index=True)


def main():
    apply_css()
    with st.sidebar:
        st.markdown("## ◈ NetSage AI")
        st.caption("Cisco network intelligence")
        api_key = st.text_input("GEMINI_API_KEY", value=os.getenv("GEMINI_API_KEY", ""), type="password")
        st.caption("Keys are used only for the current session.")
    live, dataset, analytics = st.tabs(["Live Troubleshooter", "Dataset Explorer", "Analytics Dashboard"])
    with live:
        diagnosis_tab(api_key)
    with dataset:
        dataset_tab()
    with analytics:
        analytics_tab()


if __name__ == "__main__":
    main()
