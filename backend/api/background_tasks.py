# backend/api/background_tasks.py
#
# Background task utilities for the FastAPI app.
#
# Currently handles:
#   - Async wrapper for running crew analysis
#   - Future: webhook notifications, email alerts
#
# FastAPI's BackgroundTasks run AFTER the response is sent.
# This means we can return "analysis started" immediately
# and let the crew run in the background.
# The result gets saved to DynamoDB when done.
# The client polls /api/report/{ticker} to get the result.

import logging
from backend.api.cache import cache
from backend.db.dynamo_client import save_analysis

logger = logging.getLogger(__name__)


def run_analysis_background(ticker: str) -> None:
    """
    Runs crew analysis in the background.

    Called by FastAPI's BackgroundTasks after response is sent.
    Saves result to both RAM cache and DynamoDB when complete.

    Args:
        ticker: Stock symbol to analyze
    """
    import os
    from dotenv import load_dotenv
    load_dotenv()
    os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY", "")

    from backend.crew.equityiq_crew import analyze_ticker

    logger.info(f"Background analysis started for {ticker}")

    try:
        report = analyze_ticker(ticker=ticker, force_refresh=True)
        if report:
            cache.set(ticker, report)
            logger.info(f"Background analysis complete for {ticker}")
        else:
            logger.error(f"Background analysis returned no report for {ticker}")

    except Exception as e:
        logger.error(f"Background analysis failed for {ticker}: {e}")