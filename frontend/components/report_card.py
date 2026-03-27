# frontend/components/report_card.py
#
# Reusable component that renders a compact report card.
# Used in the History page and Top 5 picks section.

import streamlit as st


def render_verdict_badge(verdict: str):
    """Renders a colored BUY/HOLD/SELL badge."""
    verdict_class = {
        "BUY": "verdict-buy",
        "SELL": "verdict-sell",
        "HOLD": "verdict-hold",
    }.get(verdict.upper(), "verdict-hold")

    st.markdown(
        f"<span class='{verdict_class}'>{verdict.upper()}</span>",
        unsafe_allow_html=True
    )


def render_metric(label: str, value: str, color: str = "#60a5fa"):
    """Renders a single metric card."""
    st.markdown(f"""
    <div class='metric-card'>
        <div class='metric-value' style='color:{color};'>{value}</div>
        <div class='metric-label'>{label}</div>
    </div>
    """, unsafe_allow_html=True)