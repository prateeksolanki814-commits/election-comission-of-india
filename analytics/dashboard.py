"""
DEMO / RESEARCH PROTOTYPE — NOT FOR REAL ELECTIONS.

Analytics dashboard. Hard rule: every query in this file is a GROUP BY /
COUNT / aggregate. Nothing here ever selects a single ballot row joined to
anything voter-identifiable — there is no such join possible by schema
design (see ARCHITECTURE.md), but this file also never attempts row-level
ballot inspection even in aggregate form, to keep the demo honest about
what real election dashboards should and shouldn't show while voting is
open.
"""
import os

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text

ANALYTICS_DB_URL = os.environ.get(
    "ANALYTICS_DATABASE_URL",
    "postgresql+psycopg2://role_analytics_svc:change_me_analytics@localhost:5432/vote_research_demo",
)

st.set_page_config(page_title="Election Analytics (DEMO)", layout="wide")
st.error("⚠️ DEMO / RESEARCH PROTOTYPE — NOT A REAL ELECTION. All figures are synthetic.")
st.title("Election Analytics Dashboard")

engine = create_engine(ANALYTICS_DB_URL)


@st.cache_data(ttl=30)
def load_participation() -> pd.DataFrame:
    query = "SELECT constituency_name, votes_cast FROM metrics.mv_participation_by_constituency ORDER BY votes_cast DESC"
    return pd.read_sql(text(query), engine)


@st.cache_data(ttl=30)
def load_auth_stats() -> pd.DataFrame:
    query = """
        SELECT date_trunc('minute', attempted_at) AS minute, success, count(*) AS n
        FROM eligibility.auth_attempts
        GROUP BY 1, 2 ORDER BY 1
    """
    return pd.read_sql(text(query), engine)


@st.cache_data(ttl=30)
def load_performance() -> pd.DataFrame:
    query = """
        SELECT metric_name, metric_value, recorded_at
        FROM metrics.system_metrics
        WHERE metric_name IN ('response_time_ms','error_rate')
        ORDER BY recorded_at DESC LIMIT 5000
    """
    return pd.read_sql(text(query), engine)


tab1, tab2, tab3, tab4 = st.tabs(["Participation", "Auth Attempts", "Performance", "Anomaly Detection"])

with tab1:
    df = load_participation()
    if df.empty:
        st.warning("No participation data yet.")
    else:
        total = df["votes_cast"].sum()
        st.metric("Total votes cast (all constituencies)", int(total))
        fig = px.bar(df, x="constituency_name", y="votes_cast", title="Votes cast by constituency")
        st.plotly_chart(fig, use_container_width=True)

with tab2:
    df = load_auth_stats()
    if df.empty:
        st.warning("No auth attempt data yet.")
    else:
        pivot = df.pivot_table(index="minute", columns="success", values="n", fill_value=0)
        pivot.columns = ["failed" if c is False else "succeeded" for c in pivot.columns]
        fig = px.line(pivot.reset_index(), x="minute", y=pivot.columns, title="Auth attempts over time")
        st.plotly_chart(fig, use_container_width=True)

        fail_rate = (
            df[df["success"] == False]["n"].sum() / max(df["n"].sum(), 1) * 100
        )
        st.metric("Failed-auth rate", f"{fail_rate:.1f}%")

with tab3:
    df = load_performance()
    if df.empty:
        st.warning("No performance metrics recorded yet. Run a load test to populate this.")
    else:
        latency = df[df["metric_name"] == "response_time_ms"]["metric_value"]
        if not latency.empty:
            p50, p95, p99 = latency.quantile([0.5, 0.95, 0.99])
            c1, c2, c3 = st.columns(3)
            c1.metric("p50 latency (ms)", f"{p50:.0f}")
            c2.metric("p95 latency (ms)", f"{p95:.0f}")
            c3.metric("p99 latency (ms)", f"{p99:.0f}")
        fig = px.line(df, x="recorded_at", y="metric_value", color="metric_name", title="Metrics over time")
        st.plotly_chart(fig, use_container_width=True)

with tab4:
    st.subheader("Suspicious pattern detection (aggregate-only)")
    df = load_auth_stats()
    if df.empty:
        st.warning("No data yet.")
    else:
        # Flag minutes where failed-auth volume spikes far above the
        # rolling average — a simple statistical anomaly heuristic, not a
        # claim of certainty. This is meant to prompt human investigation,
        # not to auto-block anyone.
        failed = df[df["success"] == False].groupby("minute")["n"].sum().reset_index()
        if not failed.empty:
            failed["rolling_avg"] = failed["n"].rolling(5, min_periods=1).mean()
            failed["spike"] = failed["n"] > (failed["rolling_avg"] * 3 + 5)
            spikes = failed[failed["spike"]]
            if not spikes.empty:
                st.warning(f"{len(spikes)} time windows show abnormal failed-login spikes.")
                st.dataframe(spikes)
            else:
                st.success("No abnormal spikes detected in current window.")
            fig = px.line(failed, x="minute", y=["n", "rolling_avg"], title="Failed auth attempts vs rolling average")
            st.plotly_chart(fig, use_container_width=True)

st.caption(
    "This dashboard shows aggregates only. It cannot and does not show how any individual voted — "
    "see PRIVACY.md for the architectural reason why."
)
