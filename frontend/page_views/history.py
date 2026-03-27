# frontend/pages/history.py
#
# Shows the last 20 analyses run across all tickers.
# Lets users quickly re-open a previous analysis.

import streamlit as st
import requests
import os

API_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def render():
    """Renders the analysis history page."""

    st.markdown("""
    <div style='padding: 1.5rem 0 1rem 0;'>
        <h2 style='font-size:2rem; font-weight:800;
                   color:#f1f5f9; margin-bottom:0.25rem;'>
            Analysis History
        </h2>
        <p style='color:#64748b; font-size:0.9rem;'>
            Your last 20 analyses. Click any row to re-analyze.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Fetch history from API
    history = _fetch_history()

    if not history:
        st.markdown("""
        <div class='equity-card' style='text-align:center; padding:3rem;'>
            <div style='font-size:2rem; margin-bottom:0.5rem;'>📋</div>
            <div style='color:#94a3b8;'>
                No analyses yet. Go to Stock Analyzer to get started.
            </div>
        </div>
        """, unsafe_allow_html=True)
        return

    # Summary stats
    total = len(history)
    buy_count = sum(1 for h in history
                    if h.get("direction", "").upper() == "BULLISH")
    sell_count = sum(1 for h in history
                     if h.get("direction", "").upper() == "BEARISH")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""
        <div class='metric-card'>
            <div class='metric-value'>{total}</div>
            <div class='metric-label'>Total Analyses</div>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class='metric-card'>
            <div class='metric-value' style='color:#6ee7b7;'>
                {buy_count}
            </div>
            <div class='metric-label'>Bullish Signals</div>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class='metric-card'>
            <div class='metric-value' style='color:#fca5a5;'>
                {sell_count}
            </div>
            <div class='metric-label'>Bearish Signals</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # History table
    st.markdown("""
    <div style='background:#1a1d27; border:1px solid #2d3748;
                border-radius:12px; overflow:hidden;'>
        <div style='display:grid;
                    grid-template-columns:1fr 1fr 1fr 1fr 1fr;
                    padding:0.75rem 1.25rem;
                    background:#0f1117;
                    font-size:0.7rem; color:#64748b;
                    text-transform:uppercase; letter-spacing:0.1em;'>
            <span>Ticker</span>
            <span>Date</span>
            <span>Time</span>
            <span>Direction</span>
            <span>Confidence</span>
        </div>
    """, unsafe_allow_html=True)

    for i, item in enumerate(history):
        ticker = item.get("ticker", "N/A")
        timestamp = item.get("timestamp", "")
        direction = item.get("direction", "UNKNOWN")
        confidence = item.get("confidence", "N/A")

        # Parse timestamp
        date_str = timestamp[:10] if timestamp else "N/A"
        time_str = timestamp[11:19] if len(timestamp) > 10 else "N/A"

        # Direction color
        dir_color = (
            "#6ee7b7" if direction == "BULLISH" else
            "#fca5a5" if direction == "BEARISH" else
            "#fcd34d"
        )

        # Alternating row background
        row_bg = "#1a1d27" if i % 2 == 0 else "#1e2130"

        st.markdown(f"""
        <div style='display:grid;
                    grid-template-columns:1fr 1fr 1fr 1fr 1fr;
                    padding:0.9rem 1.25rem;
                    background:{row_bg};
                    border-top:1px solid #0f1117;
                    font-size:0.85rem; align-items:center;'>
            <span style='font-weight:700; color:#60a5fa;'>{ticker}</span>
            <span style='color:#94a3b8;'>{date_str}</span>
            <span style='color:#64748b;'>{time_str} UTC</span>
            <span style='color:{dir_color}; font-weight:600;'>
                {direction}
            </span>
            <span style='color:#94a3b8;'>{str(confidence)[:20]}</span>
        </div>
        """, unsafe_allow_html=True)

        # Re-analyze button
        if st.button(f"Re-analyze {ticker}",
                     key=f"history_{ticker}_{i}",
                     use_container_width=False):
            st.session_state.page = "deep_dive"
            st.session_state.ticker = ticker
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


def _fetch_history() -> list:
    """Fetches analysis history from FastAPI."""
    try:
        resp = requests.get(f"{API_URL}/api/history", timeout=5)
        if resp.status_code == 200:
            return resp.json().get("items", [])
    except Exception:
        pass
    return []