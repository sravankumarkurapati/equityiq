# backend/api/routes/reports.py
#
# Read-only endpoints for retrieving stored reports.
# These are fast GET endpoints that don't trigger agent runs.
#
# Endpoints:
#   GET /api/report/{ticker}  — latest report for a ticker
#   GET /api/top5             — today's top 5 picks
#   GET /api/history          — last 20 analyses across all tickers

from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
import logging

from backend.api.schemas import AnalysisReport, Top5Response, HistoryResponse
from backend.api.cache import cache
from backend.db.dynamo_client import (
    get_latest_analysis,
    get_daily_picks,
    list_recent_analyses,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/report/{ticker}",
    response_model=AnalysisReport,
    summary="Get latest report for a ticker",
    description="Returns the most recent analysis report. Does not re-run agents."
)
async def get_report(ticker: str):
    """
    Retrieves the latest stored analysis for a ticker.
    Checks RAM cache first, then DynamoDB.
    Returns 404 if no analysis has been run yet.
    """
    ticker = ticker.upper().strip()
    logger.info(f"Report requested for {ticker}")

    # Check RAM cache first
    cached = cache.get(ticker)
    if cached:
        return cached

    # Fall back to DynamoDB
    report = get_latest_analysis(ticker)
    if not report:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No analysis found for {ticker}. "
                f"Run POST /api/analyze/{ticker} first."
            )
        )

    # Populate RAM cache for next request
    cache.set(ticker, report)
    return report


@router.get(
    "/top5",
    response_model=Top5Response,
    summary="Get today's top 5 stock picks",
    description=(
        "Returns the top 5 stocks identified by the daily screener. "
        "Updated every weekday morning at 8:30 AM ET by Lambda."
    )
)
async def get_top5():
    """
    Returns today's top 5 stock picks from DynamoDB.
    The Lambda screener populates this every morning.
    If no picks exist for today, returns an empty list with a message.
    """
    # Get today's date in ET timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    logger.info(f"Top5 requested for date: {today}")

    picks = get_daily_picks(today)

    if not picks:
        # No picks yet today — Lambda hasn't run or it's a weekend
        return Top5Response(
            date=today,
            picks=[],
            message=(
                "No picks available yet for today. "
                "The daily screener runs at 8:30 AM ET on weekdays. "
                "Try running POST /api/analyze/{ticker} for manual analysis."
            )
        )

    return Top5Response(
        date=today,
        picks=picks,
        generated_at=today,
        message=f"Top 5 picks for {today}"
    )


@router.get(
    "/history",
    response_model=HistoryResponse,
    summary="Get recent analysis history",
    description="Returns the last 20 analyses run across all tickers."
)
async def get_history(limit: int = 20):
    """
    Returns a list of recent analyses from DynamoDB.
    Used by the History page in Streamlit.
    Limit defaults to 20, max 50.
    """
    # Cap limit to prevent very large scans
    limit = min(limit, 50)
    logger.info(f"History requested (limit={limit})")

    items = list_recent_analyses(limit=limit)

    return HistoryResponse(
        items=items,
        total=len(items)
    )

@router.post(
    "/screener/run",
    summary="Run daily stock screener on demand",
    description=(
        "Scans today's most active stocks from Yahoo Finance, "
        "scores them, and saves top 5 picks to DynamoDB. "
        "Takes 5-8 minutes to complete."
    )
)
async def run_screener_now():
    """
    Triggers the real-time market screener on demand.
    Fetches today's market movers, scores each one,
    and saves top 5 picks to DynamoDB.
    """
    import os
    from dotenv import load_dotenv
    load_dotenv()
    os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY", "")

    logger.info("On-demand screener triggered")

    try:
        from backend.ml.screener import run_screener, run_and_save_daily_picks
        from datetime import datetime, timezone

        success = run_and_save_daily_picks()

        if success:
            # Return today's picks
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            picks = get_daily_picks(today)
            return {
                "success": True,
                "message": "Screener completed successfully",
                "date": today,
                "picks_count": len(picks) if picks else 0,
                "picks": picks or [],
            }
        else:
            return {
                "success": False,
                "message": "Screener failed — check server logs",
            }

    except Exception as e:
        logger.error(f"On-demand screener error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Screener failed: {str(e)}"
        )
