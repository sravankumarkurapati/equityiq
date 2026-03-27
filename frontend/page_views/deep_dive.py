import streamlit as st
import requests
import os

API_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def render():

    st.markdown("""
    <div style='padding: 1.5rem 0 1rem 0;'>
        <h2 style='font-size:2rem; font-weight:800;
                   color:#f1f5f9; margin-bottom:0.25rem;'>
            Stock Analyzer
        </h2>
        <p style='color:#64748b; font-size:0.9rem;'>
            5 AI agents analyze any stock in real time.
            Results cached for 30 minutes.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Check for ticker passed from home page ────────────────────
    # When user clicks Analyze on home page, pending_ticker is set.
    # We read it here, clear it, and auto-run the analysis.
    # This means user never has to enter the ticker twice.
    pending = st.session_state.get("pending_ticker", "")
    if pending:
        st.session_state.pending_ticker = ""
        _run_analysis(pending.upper().strip())
        return

    # ── Manual search bar ─────────────────────────────────────────
    col1, col2, col3 = st.columns([3, 1, 1])

    with col1:
        ticker = st.text_input(
            label="ticker",
            placeholder="Enter ticker — AAPL, NVDA, TSLA...",
            label_visibility="collapsed",
            key="deep_dive_ticker",
        ).upper().strip()

    with col2:
        analyze_btn = st.button(
            "🔍 Analyze",
            use_container_width=True,
            key="deep_dive_analyze",
        )

    with col3:
        refresh_btn = st.button(
            "🔄 Refresh",
            use_container_width=True,
            key="deep_dive_refresh",
        )

    # Run analysis on button click
    if analyze_btn and ticker:
        _run_analysis(ticker, force_refresh=False)
    elif refresh_btn and ticker:
        _run_analysis(ticker, force_refresh=True)
    elif "last_report" in st.session_state:
        # Show last report if we have one
        _render_report(st.session_state.last_report)
    else:
        _render_empty_state()


def _run_analysis(ticker, force_refresh=False):
    """Calls the FastAPI backend and renders the report."""

    if not ticker:
        return

    # Show loading state
    progress = st.empty()
    progress.markdown("""
    <div class='equity-card' style='text-align:center; padding:3rem;'>
        <div style='font-size:2.5rem; margin-bottom:1rem;'>🤖</div>
        <div style='font-size:1.1rem; font-weight:600;
                    color:#f1f5f9; margin-bottom:0.5rem;'>
            Analyzing """ + ticker + """...
        </div>
        <div style='font-size:0.85rem; color:#94a3b8; line-height:1.6;'>
            5 AI agents working in parallel.<br>
            News · Financials · Sentiment · Forecast · Validation<br>
            <span style='color:#64748b;'>
                First run: 60-90 seconds. Cached: instant.
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    try:
        resp = requests.post(
            API_URL + "/api/analyze/" + ticker,
            json={"force_refresh": force_refresh},
            timeout=180,
        )
        progress.empty()

        if resp.status_code == 200:
            report = resp.json().get("report", {})
            if report:
                st.session_state.last_report = report
                _render_report(report)
            else:
                st.error("No report generated. Please try again.")
        elif resp.status_code == 400:
            st.error("Invalid ticker: " + ticker)
        else:
            st.error("Analysis failed. Please try again.")

    except requests.Timeout:
        progress.empty()
        st.error(
            "Analysis timed out. Agents taking longer than expected. "
            "Try again in a moment."
        )
    except requests.ConnectionError:
        progress.empty()
        st.error(
            "Cannot connect to API. "
            "Make sure FastAPI is running: "
            "uvicorn backend.api.main:app --port 8000"
        )
    except Exception as e:
        progress.empty()
        st.error("Error: " + str(e))


def _render_report(report):
    """Renders the complete analysis report."""

    ticker = report.get("ticker", "N/A")
    verdict = str(report.get("final_verdict", "HOLD")).upper()
    confidence = report.get("confidence_score", "N/A")
    from_cache = report.get("from_cache", False)
    generated_at = str(report.get("generated_at", ""))
    forecast = report.get("forecast_chart_data") or {}

    # Pre-compute all formatted values
    raw_price = forecast.get("current_price")
    raw_pred = forecast.get("predicted_price_7d")
    raw_change = forecast.get("predicted_change_pct")
    raw_conf = forecast.get("confidence_score")
    direction = str(forecast.get("direction_signal", "N/A"))

    price_str = "${:.2f}".format(raw_price) if raw_price is not None else "N/A"
    pred_str = "${:.2f}".format(raw_pred) if raw_pred is not None else "N/A"
    change_str = "{:+.2f}%".format(raw_change) if raw_change is not None else "N/A"
    conf_str = "{:.1f}%".format(raw_conf) if raw_conf is not None else "N/A"
    change_color = "#6ee7b7" if (raw_change or 0) > 0 else "#fca5a5"
    cache_label = "⚡ From cache" if from_cache else "🔄 Fresh analysis"
    time_label = generated_at[:19].replace("T", " ") if generated_at else ""

    verdict_class = {
        "BUY": "verdict-buy",
        "SELL": "verdict-sell",
        "HOLD": "verdict-hold",
    }.get(verdict, "verdict-hold")

    # ── Header ────────────────────────────────────────────────────
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown(
            "<div style='padding:0.5rem 0;'>"
            "<div style='font-size:2.5rem; font-weight:800; color:#f1f5f9;'>"
            + ticker +
            "</div>"
            "<div style='font-size:0.8rem; color:#64748b; margin-top:4px;'>"
            + cache_label + " · " + time_label + " UTC"
            "</div></div>",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            "<div style='text-align:right; padding:1rem 0;'>"
            "<div style='font-size:0.75rem; color:#64748b; margin-bottom:0.5rem;'>"
            "AI VERDICT</div>"
            "<span class='" + verdict_class + "'>" + verdict + "</span>"
            "</div>",
            unsafe_allow_html=True,
        )

    # ── Metrics ───────────────────────────────────────────────────
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    conf_display = str(confidence)[:15]

    for col, label, value, color in [
        (m1, "Current Price", price_str, "#60a5fa"),
        (m2, "7-Day Target", pred_str, "#60a5fa"),
        (m3, "Predicted Change", change_str, change_color),
        (m4, "Direction", direction, "#60a5fa"),
        (m5, "Forecast Confidence", conf_str, "#60a5fa"),
        (m6, "AI Confidence", conf_display, "#60a5fa"),
    ]:
        with col:
            st.markdown(
                "<div class='metric-card'>"
                "<div class='metric-value' style='color:" + color + ";'>"
                + value + "</div>"
                "<div class='metric-label'>" + label + "</div>"
                "</div>",
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Forecast chart ────────────────────────────────────────────
    daily_forecast = forecast.get("daily_forecast", [])
    if daily_forecast:
        try:
            from components.forecast_chart import render_forecast_chart
            render_forecast_chart(ticker, daily_forecast, raw_price, raw_pred)
        except Exception:
            pass

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Bull / Bear / Risks ───────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    for col, header, border, key in [
        (c1, "🟢 Bull Case", "#10b981", "bull_case"),
        (c2, "🔴 Bear Case", "#ef4444", "bear_case"),
        (c3, "⚠️ Key Risks", "#f59e0b", "key_risks"),
    ]:
        with col:
            content = str(report.get(key, "N/A"))
            st.markdown(
                "<div class='section-header'>" + header + "</div>"
                "<div class='equity-card' style='border-left:3px solid "
                + border + ";'>"
                "<div style='font-size:0.85rem; color:#94a3b8; line-height:1.7;'>"
                + content + "</div></div>",
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Executive summary ─────────────────────────────────────────
    summary = str(report.get("executive_summary", "N/A"))
    st.markdown(
        "<div class='section-header'>📋 Executive Summary</div>"
        "<div class='equity-card'>"
        "<div style='font-size:0.95rem; color:#e2e8f0; line-height:1.8;'>"
        + summary + "</div></div>",
        unsafe_allow_html=True,
    )

    # ── Signal alignment ──────────────────────────────────────────
    alignment = str(report.get("signal_alignment", ""))
    if alignment:
        st.markdown(
            "<div class='section-header' style='margin-top:1rem;'>"
            "🔗 Signal Alignment</div>"
            "<div class='equity-card'>"
            "<div style='font-size:0.85rem; color:#94a3b8; line-height:1.7;'>"
            + alignment + "</div></div>",
            unsafe_allow_html=True,
        )

    # ── Detailed agent outputs ────────────────────────────────────
    sections = report.get("sections") or {}
    if sections:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            "<div class='section-header'>🤖 Detailed Agent Reports</div>",
            unsafe_allow_html=True,
        )
        for title, key in [
            ("📰 News Analysis", "news"),
            ("📊 Financial Analysis", "financials"),
            ("💭 Sentiment Analysis", "sentiment"),
            ("🔮 Price Forecast", "forecast"),
            ("⚖️ Critic Validation", "validation"),
        ]:
            content = str(sections.get(key, ""))
            if content and len(content) > 10:
                with st.expander(title):
                    st.markdown(
                        "<div style='font-size:0.85rem; color:#94a3b8;"
                        "line-height:1.7;'>" + content + "</div>",
                        unsafe_allow_html=True,
                    )

    # ── Disclaimer ────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    disclaimer = str(report.get(
        "disclaimer",
        "This analysis is for informational purposes only and does "
        "not constitute financial advice.",
    ))
    st.markdown(
        "<div style='font-size:0.72rem; color:#475569;"
        "border:1px solid #1e293b; border-radius:8px;"
        "padding:0.75rem 1rem; line-height:1.6;'>"
        "⚠️ " + disclaimer + "</div>",
        unsafe_allow_html=True,
    )


def _render_empty_state():
    st.markdown("""
    <div class='equity-card' style='text-align:center; padding:4rem 2rem;'>
        <div style='font-size:3rem; margin-bottom:1rem;'>🔍</div>
        <div style='font-size:1.2rem; font-weight:600;
                    color:#f1f5f9; margin-bottom:0.5rem;'>
            Enter a ticker to get started
        </div>
        <div style='font-size:0.9rem; color:#64748b;
                    max-width:400px; margin:0 auto; line-height:1.6;'>
            Type any stock symbol above and click Analyze.
            Works for all NYSE, NASDAQ stocks and ETFs.
        </div>
        <div style='margin-top:1.5rem; font-size:0.8rem; color:#475569;'>
            AAPL · NVDA · TSLA · MSFT · GOOGL · AMZN · SPY · QQQ
        </div>
    </div>
    """, unsafe_allow_html=True)