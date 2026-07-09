"""
ClaimStream frontend — Streamlit UI over the claims microservices.

Talks to the backend purely over REST/HTTP, same as any external client would.
No business logic here on purpose: this app is a window into the event-driven
pipeline, not a participant in it.

Env vars (set in docker-compose.yml):
    INTAKE_URL       - e.g. http://intake:8000
    PAYOUT_URL       - e.g. http://payout:8000
    GRAFANA_URL      - e.g. http://grafana:3000
    RCA_REPORTS_DIR  - path to mounted rca/reports/ folder, e.g. /app/rca-reports
"""

import os
import glob
import time
from datetime import datetime

import requests
import streamlit as st

INTAKE_URL = os.environ.get("INTAKE_URL", "http://intake:8000")
PAYOUT_URL = os.environ.get("PAYOUT_URL", "http://payout:8000")
GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://localhost:3000")
RCA_REPORTS_DIR = os.environ.get("RCA_REPORTS_DIR", "/app/rca-reports")

st.set_page_config(page_title="ClaimStream", layout="wide")
st.title("ClaimStream")
st.caption("Event-driven claims platform — spec-driven, AI-assisted, self-diagnosing")

tab_submit, tab_track, tab_rca, tab_ops = st.tabs(
    ["Submit claim", "Track claim", "RCA reports", "Operations"]
)

# ---------------------------------------------------------------------------
# Tab 1: Submit a claim
# ---------------------------------------------------------------------------
with tab_submit:
    st.subheader("Submit a new claim")

    with st.form("claim_form"):
        col1, col2 = st.columns(2)
        with col1:
            policy_number = st.text_input("Policy number", placeholder="POL-100234")
            claimant_name = st.text_input("Claimant name", placeholder="Jane Doe")
        with col2:
            claim_amount = st.number_input("Claim amount ($)", min_value=0.0, step=100.0)
            claim_type = st.selectbox("Claim type", ["death_benefit", "annuity_withdrawal", "surrender"])

        description = st.text_area("Description", placeholder="Brief description of the claim")
        submitted = st.form_submit_button("Submit claim")

    if submitted:
        payload = {
            "policy_number": policy_number,
            "claimant_name": claimant_name,
            "amount": claim_amount,
            "claim_type": claim_type,
            "description": description,
        }
        try:
            resp = requests.post(f"{INTAKE_URL}/claims", json=payload, timeout=5)
            if resp.status_code in (200, 201, 202):
                data = resp.json()
                claim_id = data.get("claim_id", "unknown")
                st.success(f"Claim accepted — id: `{claim_id}`")
                st.session_state["last_claim_id"] = claim_id
                st.info("Switch to the 'Track claim' tab to follow it through the pipeline.")
            else:
                st.error(f"Intake service rejected the claim: {resp.status_code} — {resp.text}")
        except requests.exceptions.RequestException as e:
            st.error(f"Could not reach intake service at {INTAKE_URL}: {e}")

# ---------------------------------------------------------------------------
# Tab 2: Track a claim through the event pipeline
# ---------------------------------------------------------------------------
with tab_track:
    st.subheader("Track a claim")

    default_id = st.session_state.get("last_claim_id", "")
    claim_id = st.text_input("Claim ID", value=default_id, placeholder="e.g. clm_8f21ac")

    col_a, col_b = st.columns([1, 4])
    with col_a:
        check = st.button("Check status")
    with col_b:
        auto_refresh = st.checkbox("Auto-refresh every 3s")

    if claim_id and (check or auto_refresh):
        try:
            resp = requests.get(f"{INTAKE_URL}/claims/{claim_id}", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                st.json(data)

                # Render the event trail as a simple timeline, oldest first.
                events = data.get("events", [])
                if events:
                    st.write("**Event timeline**")
                    for ev in events:
                        ts = ev.get("timestamp", "")
                        st.write(f"- `{ts}` — {ev.get('type', 'event')}: {ev.get('detail', '')}")
                else:
                    st.write("No events recorded yet — the claim may still be in the intake queue.")
            else:
                st.warning(f"Claim not found or service returned {resp.status_code}")
        except requests.exceptions.RequestException as e:
            st.error(f"Could not reach intake service at {INTAKE_URL}: {e}")

        if auto_refresh:
            time.sleep(3)
            st.rerun()

# ---------------------------------------------------------------------------
# Tab 3: Browse AI-generated RCA reports
# ---------------------------------------------------------------------------
with tab_rca:
    st.subheader("RCA reports")
    st.caption("Generated after chaos-injected failures. Each has an AI draft and a human review section.")

    report_files = sorted(glob.glob(os.path.join(RCA_REPORTS_DIR, "*.md")), reverse=True)

    if not report_files:
        st.info(
            f"No RCA reports found in {RCA_REPORTS_DIR}. "
            f"Run `python chaos/inject_fault.py` followed by `python rca/generate_rca.py` to create one."
        )
    else:
        selected = st.selectbox(
            "Select a report",
            report_files,
            format_func=lambda p: os.path.basename(p),
        )
        with open(selected, "r") as f:
            content = f.read()
        st.markdown(content)

# ---------------------------------------------------------------------------
# Tab 4: Operations — service health + link out to Grafana
# ---------------------------------------------------------------------------
with tab_ops:
    st.subheader("Service health")

    services = {
        "intake": f"{INTAKE_URL}/health",
        "payout": f"{PAYOUT_URL}/health",
    }

    cols = st.columns(len(services))
    for col, (name, url) in zip(cols, services.items()):
        with col:
            try:
                resp = requests.get(url, timeout=2)
                ok = resp.status_code == 200
            except requests.exceptions.RequestException:
                ok = False
            st.metric(label=name, value="up" if ok else "down")

    st.divider()
    st.write("**Dashboards**")
    st.markdown(f"[Open Grafana]({GRAFANA_URL})")
    st.caption(f"Last checked: {datetime.now().strftime('%H:%M:%S')}")
