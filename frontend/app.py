"""
DEMO / RESEARCH PROTOTYPE — NOT FOR REAL ELECTIONS.

Streamlit voter-facing prototype (v1). A React SPA is the intended v2
frontend for production-shaped UX; this gets the full flow demoable fast.
"""
import os

import requests
import streamlit as st

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

STRINGS = {
    "en": {
        "title": "Remote Voting Research Prototype",
        "banner": "⚠️ DEMO / RESEARCH PROTOTYPE — NOT A REAL ELECTION. Synthetic data only.",
        "voter_code_label": "Synthetic Voter Code",
        "login_btn": "Send OTP",
        "otp_label": "Enter OTP",
        "verify_btn": "Verify & Get Voting Token",
        "candidate_label": "Select your candidate",
        "cast_btn": "Cast Ballot",
        "receipt_title": "Your receipt",
        "consent_notice": (
            "By continuing, you acknowledge this is a research prototype using only "
            "synthetic data. No real votes, identities, or results are involved. "
            "Your ballot choice is never linked to your identity in this system."
        ),
    },
    "hi": {
        "title": "रिमोट वोटिंग अनुसंधान प्रोटोटाइप",
        "banner": "⚠️ डेमो / अनुसंधान प्रोटोटाइप — यह वास्तविक चुनाव नहीं है। केवल सिंथेटिक डेटा।",
        "voter_code_label": "सिंथेटिक वोटर कोड",
        "login_btn": "OTP भेजें",
        "otp_label": "OTP दर्ज करें",
        "verify_btn": "सत्यापित करें और वोटिंग टोकन प्राप्त करें",
        "candidate_label": "अपना उम्मीदवार चुनें",
        "cast_btn": "मतदान करें",
        "receipt_title": "आपकी रसीद",
        "consent_notice": (
            "आगे बढ़ने पर, आप स्वीकार करते हैं कि यह केवल सिंथेटिक डेटा का उपयोग करने वाला "
            "एक अनुसंधान प्रोटोटाइप है। इसमें कोई वास्तविक वोट, पहचान या परिणाम शामिल नहीं हैं। "
            "इस प्रणाली में आपकी वोट पसंद कभी भी आपकी पहचान से नहीं जोड़ी जाती।"
        ),
    },
}

st.set_page_config(page_title="Vote Research Prototype (DEMO)", layout="centered")

lang = st.sidebar.selectbox("Language / भाषा", ["en", "hi"], format_func=lambda x: "English" if x == "en" else "हिंदी")
high_contrast = st.sidebar.checkbox("High contrast mode")
large_text = st.sidebar.checkbox("Larger text")
S = STRINGS[lang]

if high_contrast:
    st.markdown(
        "<style>body { background-color: #000 !important; color: #fff !important; }</style>",
        unsafe_allow_html=True,
    )
if large_text:
    st.markdown("<style>html, body, [class*='css'] { font-size: 20px !important; }</style>", unsafe_allow_html=True)

st.error(S["banner"])
st.title(S["title"])
st.info(S["consent_notice"])

if "step" not in st.session_state:
    st.session_state.step = "login"

election_id = st.text_input("Election ID (from admin/demo setup)", key="election_id")

if st.session_state.step == "login":
    voter_code = st.text_input(S["voter_code_label"], key="voter_code")
    if st.button(S["login_btn"]) and voter_code:
        resp = requests.post(f"{API_BASE_URL}/api/v1/auth/login", json={"synthetic_voter_code": voter_code})
        if resp.status_code == 200:
            st.session_state.demo_otp = resp.json()["demo_otp"]
            st.session_state.step = "otp"
            st.success(f"(DEMO) Your OTP is: {st.session_state.demo_otp} — a real system sends this via SMS.")
        else:
            st.error(resp.json())

elif st.session_state.step == "otp":
    otp = st.text_input(S["otp_label"], max_chars=6, key="otp")
    if st.button(S["verify_btn"]) and otp and election_id:
        resp = requests.post(
            f"{API_BASE_URL}/api/v1/auth/verify-otp",
            json={
                "synthetic_voter_code": st.session_state.voter_code,
                "otp": otp,
                "election_id": election_id,
            },
        )
        if resp.status_code == 200:
            st.session_state.voting_token = resp.json()["voting_token"]
            st.session_state.step = "vote"
            st.success("Voting token issued. Your identity check is now complete and separate from your ballot.")
        else:
            st.error(resp.json())

elif st.session_state.step == "vote":
    constituency_id = st.text_input("Constituency ID")
    candidate_id = st.text_input("Candidate ID (" + S["candidate_label"] + ")")
    if st.button(S["cast_btn"]) and constituency_id and candidate_id:
        import uuid

        resp = requests.post(
            f"{API_BASE_URL}/api/v1/ballot/cast",
            json={
                "voting_token": st.session_state.voting_token,
                "election_id": election_id,
                "constituency_id": constituency_id,
                "candidate_id": candidate_id,
            },
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        if resp.status_code == 200:
            st.session_state.step = "done"
            st.session_state.receipt = resp.json()
        else:
            st.error(resp.json())

elif st.session_state.step == "done":
    st.success(S["receipt_title"])
    st.json(st.session_state.receipt)
    st.caption("This reference number does not reveal your candidate selection.")
