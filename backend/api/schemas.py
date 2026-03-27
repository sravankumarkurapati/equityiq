# backend/api/schemas.py
#
# Pydantic models define the exact shape of:
#   - What data comes INTO the API (request bodies)
#   - What data goes OUT of the API (response bodies)
#
# Why this matters:
#   - FastAPI automatically validates all incoming data against these schemas
#   - If a field is missing or wrong type, FastAPI returns a clear 422 error
#   - The /docs page uses these to show exactly what each endpoint expects
#   - Prevents garbage data from reaching the crew

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ── Request schemas ───────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    """
    Body of POST /api/analyze/{ticker}
    force_refresh=True skips the cache and re-runs agents.
    """
    force_refresh: bool = Field(
        default=False,
        description="If true, skip cache and re-run all agents"
    )


# ── Response schemas ──────────────────────────────────────────────

class ForecastDay(BaseModel):
    """Single day in the 7-day price forecast."""
    date: str
    predicted_price: float
    lower_bound: float
    upper_bound: float


class ForecastData(BaseModel):
    """Prophet forecast data used for chart rendering in Streamlit."""
    current_price: Optional[float] = None
    predicted_price_7d: Optional[float] = None
    predicted_change_pct: Optional[float] = None
    direction_signal: Optional[str] = None
    confidence_score: Optional[float] = None
    daily_forecast: list[ForecastDay] = []
    momentum: Optional[str] = None


class ReportSections(BaseModel):
    """Raw text output from each agent — shown in detail view."""
    news: str = ""
    financials: str = ""
    sentiment: str = ""
    forecast: str = ""
    validation: str = ""


class AnalysisReport(BaseModel):
    """
    Complete analysis report returned by the API.
    This is what Streamlit receives and renders as the research report.
    """
    ticker: str
    generated_at: str
    from_cache: bool = False

    # The most important fields — shown prominently in UI
    final_verdict: str = "HOLD"          # BUY / HOLD / SELL
    confidence_score: str = "N/A"
    signal_alignment: str = ""
    bull_case: str = ""
    bear_case: str = ""
    key_risks: str = ""
    executive_summary: str = ""
    disclaimer: str = ""

    # Chart data for Streamlit forecast visualization
    forecast_chart_data: Optional[ForecastData] = None

    # Full agent outputs for detail view
    sections: Optional[ReportSections] = None

    # Status
    status: str = "complete"


class AnalyzeResponse(BaseModel):
    """
    Response from POST /api/analyze/{ticker}
    Returns the full report plus metadata.
    """
    success: bool
    ticker: str
    message: str
    report: Optional[AnalysisReport] = None


class Top5Pick(BaseModel):
    """Single stock pick in the daily top 5."""
    ticker: str
    current_price: Optional[float] = None
    predicted_price_7d: Optional[float] = None
    predicted_change_pct: Optional[float] = None
    direction: str = "NEUTRAL"
    analyst_recommendation: Optional[str] = None
    rationale: str = ""


class Top5Response(BaseModel):
    """Response from GET /api/top5"""
    date: str
    picks: list[Top5Pick] = []
    generated_at: Optional[str] = None
    message: str = ""


class HistoryItem(BaseModel):
    """Single item in the analysis history list."""
    ticker: str
    timestamp: str
    direction: str = "UNKNOWN"
    confidence: str = "N/A"


class HistoryResponse(BaseModel):
    """Response from GET /api/history"""
    items: list[HistoryItem] = []
    total: int = 0


class ErrorResponse(BaseModel):
    """Returned when something goes wrong."""
    success: bool = False
    error: str
    ticker: Optional[str] = None