import streamlit as st
import requests
import os

API_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


def render():

    st.markdown("""
    <div style='padding: 2rem 0 1rem 0;'>
        <h1 style='font-size:2.8rem; font-weight:800; color:#f1f5f9;
                   margin-bottom:0.5rem;'>
            AI-Powered Stock Research
        </h1>
        <p style='font-size:1.1rem; color:#94a3b8; max-width:600px;
                  line-height:1.6;'>
            5 specialized AI agents analyze news, financials, sentiment,
            and price forecasts to give you a clear
            <strong style='color:#60a5fa;'>BUY / HOLD / SELL</strong>
            verdict in under 90 seconds.
        </p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([3, 1])
    with col1:
        ticker_input = st.text_input(
            label="ticker",
            placeholder="Enter ticker — e.g. AAPL, NVDA, TSLA",
            label_visibility="collapsed",
            key="home_ticker_input",
        )
    with col2:
        analyze_btn = st.button(
            "Analyze →",
            use_container_width=True,
            key="home_analyze_btn",
        )

    if analyze_btn and ticker_input.strip():
        st.session_state.page = "deep_dive"
        st.session_state.pending_ticker = ticker_input.upper().strip()
        st.rerun()

    st.markdown("""
    <div style='margin: 0.5rem 0 2rem 0; font-size:0.8rem; color:#64748b;'>
        Popular:
        <span style='color:#60a5fa; margin:0 8px;'>AAPL</span>
        <span style='color:#60a5fa; margin:0 8px;'>NVDA</span>
        <span style='color:#60a5fa; margin:0 8px;'>TSLA</span>
        <span style='color:#60a5fa; margin:0 8px;'>MSFT</span>
        <span style='color:#60a5fa; margin:0 8px;'>GOOGL</span>
        <span style='color:#60a5fa; margin:0 8px;'>AMD</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    col_title, col_btn = st.columns([3, 1])
    with col_title:
        st.markdown("""
        <div style='margin-bottom:1rem;'>
            <span style='font-size:0.75rem; color:#64748b;
                         text-transform:uppercase; letter-spacing:0.1em;
                         font-weight:600;'>Daily Picks</span>
            <span style='font-size:0.75rem; color:#475569; margin-left:8px;'>
                Real-time market movers · scored by AI
            </span>
        </div>
        """, unsafe_allow_html=True)

    with col_btn:
        if st.button("🔄 Refresh Picks", key="refresh_picks"):
            with st.spinner("Scanning market movers... 5-8 mins"):
                try:
                    resp = requests.post(
                        API_URL + "/api/screener/run",
                        timeout=600,  # 10 min timeout
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        st.success(
                            "Found " +
                            str(data.get("picks_count", 0)) +
                            " picks!"
                        )
                        st.rerun()
                    else:
                        st.error("Screener failed. Try again.")
                except Exception as e:
                    st.error("Error: " + str(e))

    top5 = _fetch_top5()

    if top5 and top5.get("picks"):
        picks = top5["picks"]
        cols = st.columns(len(picks))
        for i, pick in enumerate(picks):
            with cols[i]:
                _render_pick_card(pick, i)
    else:
        st.markdown("""
        <div class='equity-card' style='text-align:center; padding:2rem;'>
            <div style='font-size:2rem; margin-bottom:0.5rem;'>🕐</div>
            <div style='color:#94a3b8; font-size:0.9rem;'>
                Daily picks generated at 8:30 AM ET on weekdays.
            </div>
            <div style='color:#64748b; font-size:0.8rem; margin-top:0.5rem;'>
                Use Stock Analyzer to research any ticker now.
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    st.markdown("""
    <div style='margin-bottom:1rem;'>
        <span style='font-size:0.75rem; color:#64748b;
                     text-transform:uppercase; letter-spacing:0.1em;
                     font-weight:600;'>How It Works</span>
    </div>
    """, unsafe_allow_html=True)

    steps = [
        ("📰", "News Agent",
         "Scans 50+ financial news sources for the past 7 days"),
        ("📊", "Financials Agent",
         "Analyzes P/E, EPS, revenue growth, and SEC filings"),
        ("💭", "Sentiment Agent",
         "Scores professional news sentiment and RSI/MACD signals"),
        ("🔮", "Predictor Agent",
         "Generates 7-day forecast using Facebook Prophet"),
        ("⚖️", "Critic Agent",
         "Validates all signals and delivers BUY/HOLD/SELL verdict"),
    ]

    cols = st.columns(5)
    for i, (icon, title, desc) in enumerate(steps):
        with cols[i]:
            st.markdown(f"""
            <div class='equity-card' style='text-align:center;
                                            min-height:160px;'>
                <div style='font-size:1.8rem;
                            margin-bottom:0.5rem;'>{icon}</div>
                <div style='font-size:0.85rem; font-weight:600;
                            color:#e2e8f0;
                            margin-bottom:0.4rem;'>{title}</div>
                <div style='font-size:0.75rem; color:#94a3b8;
                            line-height:1.5;'>{desc}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")

    st.markdown("""
    <div style='text-align:center; padding:1rem 0;
                color:#475569; font-size:0.75rem;'>
        Built by
        <strong style='color:#94a3b8;'>Sravan Kumar Kurapati</strong>
        · MS Information Systems · Northeastern University ·
        <a href='mailto:kurapati.sr@northeastern.edu'
           style='color:#60a5fa; text-decoration:none;'>
            kurapati.sr@northeastern.edu
        </a>
        · 857-427-7767
    </div>
    """, unsafe_allow_html=True)


def _render_pick_card(pick, index):
    """
    Renders a Top 5 pick card.
    All values pre-computed before f-string to avoid format errors.
    """
    ticker = pick.get("ticker", "N/A")
    direction = pick.get("direction", "NEUTRAL")
    analyst = str(pick.get("analyst_recommendation", "N/A"))
    rationale = str(pick.get("rationale", ""))

    # Pre-compute EVERY formatted value here
    # Never put conditions inside f-string format specs
    raw_price = pick.get("current_price")
    raw_pred = pick.get("predicted_price_7d")
    raw_change = pick.get("predicted_change_pct")

    if raw_price is not None:
        price_str = "${:.2f}".format(raw_price)
    else:
        price_str = "N/A"

    if raw_pred is not None:
        pred_str = "${:.2f}".format(raw_pred)
    else:
        pred_str = "N/A"

    if raw_change is not None:
        change_str = "{:+.1f}%".format(raw_change)
    else:
        change_str = "N/A"

    if direction == "BULLISH":
        color = "#6ee7b7"
        arrow = "up"
    elif direction == "BEARISH":
        color = "#fca5a5"
        arrow = "down"
    else:
        color = "#fcd34d"
        arrow = "neutral"

    if len(rationale) > 100:
        rationale_short = rationale[:100] + "..."
    else:
        rationale_short = rationale

    st.markdown(
        "<div class='equity-card'>"
        "<div style='display:flex; justify-content:space-between;"
        "align-items:center; margin-bottom:0.5rem;'>"
        "<span style='font-size:1.1rem; font-weight:700;"
        "color:#f1f5f9;'>" + ticker + "</span>"
        "<span style='font-size:0.8rem; font-weight:600;"
        "color:" + color + ";'>" + direction + "</span>"
        "</div>"
        "<div style='font-size:1.4rem; font-weight:700;"
        "color:#60a5fa; margin-bottom:0.25rem;'>"
        + price_str +
        "</div>"
        "<div style='font-size:0.8rem; margin-bottom:0.75rem;"
        "color:" + color + ";'>"
        "7d: " + pred_str + " (" + change_str + ")"
        "</div>"
        "<div style='font-size:0.7rem; color:#64748b;"
        "text-transform:uppercase; margin-bottom:0.25rem;'>"
        "Analyst: " + analyst.upper() +
        "</div>"
        "<div style='font-size:0.75rem; color:#94a3b8;"
        "line-height:1.4; margin-top:0.5rem;'>"
        + rationale_short +
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    if st.button(
        "Analyze " + ticker,
        key="pick_btn_" + ticker + "_" + str(index),
        use_container_width=True,
    ):
        st.session_state.page = "deep_dive"
        st.session_state.pending_ticker = ticker
        st.rerun()


def _fetch_top5():
    try:
        resp = requests.get(API_URL + "/api/top5", timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return {}