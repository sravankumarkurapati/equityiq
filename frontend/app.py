import streamlit as st
import os
import sys
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

st.set_page_config(
    page_title="EquityIQ",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .stApp { background-color: #0f1117; color: #ffffff; }
    [data-testid="stSidebar"] {
        background-color: #1a1d27;
        border-right: 1px solid #2d3748;
    }
    .equity-card {
        background: #1a1d27;
        border: 1px solid #2d3748;
        border-radius: 12px;
        padding: 1.5rem;
        margin-bottom: 1rem;
    }
    .verdict-buy {
        background: #065f46; color: #6ee7b7;
        padding: 6px 20px; border-radius: 20px;
        font-weight: 700; font-size: 1.1rem;
        display: inline-block;
    }
    .verdict-sell {
        background: #7f1d1d; color: #fca5a5;
        padding: 6px 20px; border-radius: 20px;
        font-weight: 700; font-size: 1.1rem;
        display: inline-block;
    }
    .verdict-hold {
        background: #78350f; color: #fcd34d;
        padding: 6px 20px; border-radius: 20px;
        font-weight: 700; font-size: 1.1rem;
        display: inline-block;
    }
    .metric-card {
        background: #1e2130;
        border: 1px solid #2d3748;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
    }
    .metric-value {
        font-size: 1.6rem;
        font-weight: 700;
        color: #60a5fa;
    }
    .metric-label {
        font-size: 0.75rem;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-top: 4px;
    }
    .section-header {
        font-size: 0.75rem;
        font-weight: 600;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin-bottom: 0.5rem;
    }
    .stTextInput input {
        background: #1e2130 !important;
        border: 1px solid #2d3748 !important;
        color: white !important;
        border-radius: 8px !important;
        font-size: 1.1rem !important;
    }
    .stButton button {
        background: #2563eb !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 0.5rem 2rem !important;
        width: 100%;
    }
    .stButton button:hover { background: #1d4ed8 !important; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    hr { border-color: #2d3748; }
    div[data-testid="stExpander"] {
        background: #1a1d27;
        border: 1px solid #2d3748;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

# ── Session state defaults ────────────────────────────────────────
if "page" not in st.session_state:
    st.session_state.page = "home"
if "pending_ticker" not in st.session_state:
    st.session_state.pending_ticker = ""

# ── Sidebar ───────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style='text-align:center; padding:1rem 0 2rem 0;'>
        <div style='font-size:2.5rem;'>📈</div>
        <div style='font-size:1.4rem; font-weight:700; color:white;'>
            EquityIQ
        </div>
        <div style='font-size:0.75rem; color:#64748b; margin-top:4px;'>
            AI Stock Intelligence Platform
        </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("🏠  Home", key="nav_home", use_container_width=True):
        st.session_state.page = "home"
        st.session_state.pending_ticker = ""
        st.rerun()

    if st.button("🔍  Stock Analyzer", key="nav_deep", use_container_width=True):
        st.session_state.page = "deep_dive"
        st.session_state.pending_ticker = ""
        st.rerun()

    if st.button("📋  History", key="nav_hist", use_container_width=True):
        st.session_state.page = "history"
        st.session_state.pending_ticker = ""
        st.rerun()

    st.markdown("---")

    st.markdown("""
    <div style='padding:0.25rem 0 0.75rem 0;'>
        <div style='font-size:0.68rem; color:#64748b; text-transform:uppercase;
                    letter-spacing:0.1em; margin-bottom:0.6rem; font-weight:600;'>
            Tech Stack
        </div>
        <div style='font-size:0.78rem; color:#94a3b8; line-height:2;'>
            🤖 CrewAI · Llama 3.3 70B<br>
            📊 Facebook Prophet (ML)<br>
            ⚡ FastAPI · Uvicorn<br>
            🗄️ AWS DynamoDB · S3<br>
            🐳 Docker · Nginx<br>
            ☁️ AWS EC2 · CloudFront<br>
            🔄 GitHub Actions CI/CD<br>
            📰 NewsAPI · Alpha Vantage<br>
            📈 yfinance · SEC EDGAR
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    st.markdown("""
    <div style='padding:0.25rem 0 0.75rem 0;'>
        <div style='font-size:0.68rem; color:#64748b; text-transform:uppercase;
                    letter-spacing:0.1em; margin-bottom:0.6rem; font-weight:600;'>
            Built by
        </div>
        <div style='font-size:0.9rem; font-weight:700; color:#f1f5f9;'>
            Sravan Kumar Kurapati
        </div>
        <div style='font-size:0.72rem; color:#64748b; margin-top:2px;'>
            MS Information Systems
        </div>
        <div style='font-size:0.72rem; color:#64748b;'>
            Northeastern University
        </div>
        <div style='margin-top:10px;'>
            <a href='mailto:kurapati.sr@northeastern.edu'
               style='font-size:0.75rem; color:#60a5fa; text-decoration:none;'>
                ✉️ kurapati.sr@northeastern.edu
            </a>
        </div>
        <div style='font-size:0.75rem; color:#94a3b8; margin-top:4px;'>
            📱 857-427-7767
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    st.markdown("""
    <div style='font-size:0.65rem; color:#475569; line-height:1.6;'>
        ⚠️ <strong style='color:#64748b;'>Disclaimer:</strong>
        For informational purposes only.
        Not financial advice. Always consult
        a licensed advisor.
    </div>
    """, unsafe_allow_html=True)

# ── Page routing ──────────────────────────────────────────────────
# Import pages here at the bottom AFTER session state is set
# This ensures pages always get the latest session state values

page = st.session_state.page

if page == "home":
    import importlib
    import page_views.home as home_mod
    importlib.reload(home_mod)
    home_mod.render()

elif page == "deep_dive":
    import importlib
    import page_views.deep_dive as deep_mod
    importlib.reload(deep_mod)
    deep_mod.render()

elif page == "history":
    import importlib
    import page_views.history as hist_mod
    importlib.reload(hist_mod)
    hist_mod.render()