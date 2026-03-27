# backend/api/routes/analyze.py
#
# The /analyze endpoint — the most important endpoint in the API.
#
# Flow when someone calls POST /api/analyze/AAPL:
#   1. Check in-memory cache — return instantly if fresh
#   2. Check DynamoDB — return if fresh analysis exists
#   3. If no fresh analysis — run the full CrewAI crew
#   4. Save result to cache + DynamoDB
#   5. Return the report
#
# Why POST and not GET:
#   GET requests should be idempotent (same result every time).
#   This endpoint may trigger a long-running agent job which
#   changes state (saves to DynamoDB), so POST is correct.
#
# The endpoint is synchronous but runs in a thread pool
# so it doesn't block other requests while agents work.

import os
from dotenv import load_dotenv
load_dotenv()
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY", "")

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
import logging

from backend.api.schemas import AnalyzeResponse, AnalyzeRequest
from backend.api.cache import cache
from backend.db.dynamo_client import get_latest_analysis, is_analysis_fresh
from backend.crew.equityiq_crew import analyze_ticker

logger = logging.getLogger(__name__)

# APIRouter groups related endpoints
# These get registered in main.py with app.include_router()
router = APIRouter()


@router.post(
    "/analyze/{ticker}",
    response_model=AnalyzeResponse,
    summary="Analyze a stock",
    description=(
        "Runs full multi-agent analysis for a stock ticker. "
        "Returns cached result if analysis is fresh (< 30 min). "
        "Set force_refresh=true to re-run agents regardless of cache."
    )
)
async def analyze_stock(
    ticker: str,
    request: AnalyzeRequest = AnalyzeRequest(),
):
    """
    Main analysis endpoint.

    Args:
        ticker: Stock symbol in URL path e.g. /analyze/AAPL
        request: Optional body with force_refresh flag

    Returns:
        AnalyzeResponse with full research report
    """
    # Normalize ticker — uppercase, no spaces
    ticker = ticker.upper().strip()

    # Basic validation — ticker should be 1-5 letters
    if not ticker.isalpha() or len(ticker) > 10:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ticker symbol: {ticker}. Use symbols like AAPL, NVDA, MSFT."
        )

    logger.info(f"Analyze request for {ticker} (force_refresh={request.force_refresh})")

    try:
        # ── Level 1: Check in-memory cache ────────────────────────
        if not request.force_refresh:
            cached = cache.get(ticker)
            if cached:
                logger.info(f"Returning RAM cache hit for {ticker}")
                cached["from_cache"] = True
                return AnalyzeResponse(
                    success=True,
                    ticker=ticker,
                    message=f"Analysis retrieved from cache for {ticker}",
                    report=cached,
                )

        # ── Level 2: Check DynamoDB ────────────────────────────────
        if not request.force_refresh and is_analysis_fresh(ticker):
            db_result = get_latest_analysis(ticker)
            if db_result:
                # Load into RAM cache for next request
                cache.set(ticker, db_result)
                logger.info(f"Returning DynamoDB cache hit for {ticker}")
                db_result["from_cache"] = True
                return AnalyzeResponse(
                    success=True,
                    ticker=ticker,
                    message=f"Analysis retrieved from database for {ticker}",
                    report=db_result,
                )

        # ── Level 3: Run full crew analysis ───────────────────────
        logger.info(f"Running full agent analysis for {ticker}...")

        # analyze_ticker is synchronous (runs agents)
        # FastAPI runs it in a thread pool so the event loop stays free
        report = analyze_ticker(
            ticker=ticker,
            force_refresh=request.force_refresh
        )

        if not report:
            raise HTTPException(
                status_code=500,
                detail=f"Analysis failed for {ticker} — no report generated"
            )

        # Save to RAM cache
        cache.set(ticker, report)

        return AnalyzeResponse(
            success=True,
            ticker=ticker,
            message=f"Fresh analysis completed for {ticker}",
            report=report,
        )

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise

    except Exception as e:
        logger.error(f"Analysis error for {ticker}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed for {ticker}: {str(e)}"
        )


@router.get(
    "/analyze/status",
    summary="API status",
)
async def analysis_status():
    """Returns current cache status — useful for debugging."""
    return {
        "status": "ready",
        "cache_size": cache.size,
        "message": "POST /api/analyze/{ticker} to run analysis"
    }