# backend/crew/equityiq_crew.py
#
# This is the brain of the entire system.
# It orchestrates all 5 agents in the correct order
# and assembles their outputs into a final report.
#
# How the crew runs:
#
#   Step 1: NewsAgent      — fetches and analyzes recent news
#   Step 2: FinancialsAgent — analyzes fundamentals + SEC filings
#   Step 3: SentimentAgent  — scores market mood + technicals
#   Step 4: PredictorAgent  — generates 7-day price forecast
#   Step 5: CriticAgent     — validates all outputs, gives verdict
#   Step 6: ReportWriter    — formats everything into final report
#
# Steps 1-4 run in PARALLEL (concurrent) to save time.
# Step 5 runs AFTER steps 1-4 complete (needs their outputs).
# Step 6 runs after step 5 (needs critic's validation).
#
# CrewAI Process types:
#   Process.sequential — agents run one after another
#   Process.hierarchical — a manager LLM delegates to agents
#
# We use sequential for simplicity and reliability.
# The parallelism for steps 1-4 is handled manually using
# Python's concurrent.futures (faster than sequential CrewAI).

from dotenv import load_dotenv
load_dotenv()

import sys
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from crewai import Crew, Process

from backend.agents.news_agent import create_news_agent, create_news_task
from backend.agents.financials_agent import (
    create_financials_agent,
    create_financials_task,
)
from backend.agents.sentiment_agent import (
    create_sentiment_agent,
    create_sentiment_task,
)
from backend.agents.predictor_agent import (
    create_predictor_agent,
    create_predictor_task,
)
from backend.agents.critic_agent import create_critic_agent, create_critic_task
from backend.crew.report_writer import ReportWriter
from backend.ml.prophet_forecaster import ProphetForecasterTool
from backend.tools.yfinance_tool import YFinanceTool
from backend.db.dynamo_client import save_analysis, is_analysis_fresh, get_latest_analysis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_single_agent_task(agent, task) -> str:
    """
    Runs a single agent on a single task and returns the output as text.

    We wrap each agent in its own mini Crew with one agent and one task.
    This lets us run multiple agents concurrently using ThreadPoolExecutor
    rather than waiting for each to finish sequentially.

    Returns the agent's output as a string.
    """
    # A Crew needs at least one agent and one task
    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        # verbose=False here — we already set verbose=True on each agent
        verbose=False,
    )
    # kickoff() runs the crew and returns the final output
    result = crew.kickoff()

    # CrewAI returns a CrewOutput object — extract the string
    return str(result)


def analyze_ticker(ticker: str, force_refresh: bool = False) -> dict:
    """
    Main entry point. Runs the full multi-agent analysis for a ticker.

    Args:
        ticker: Stock symbol e.g. "AAPL"
        force_refresh: If True, skip cache and re-run agents even if
                       a fresh analysis exists in DynamoDB

    Returns:
        Complete structured report dict

    Flow:
        1. Check cache — return cached result if fresh
        2. Run agents 1-4 in parallel
        3. Run CriticAgent on their outputs
        4. Build final report
        5. Save to DynamoDB
        6. Return report
    """
    ticker = ticker.upper().strip()
    logger.info(f"Starting analysis for {ticker}")

    # ── Step 1: Cache check ───────────────────────────────────────
    # If we analyzed this ticker recently, return the cached result.
    # This saves API calls and makes the app feel fast for repeat queries.
    if not force_refresh and is_analysis_fresh(ticker):
        logger.info(f"Cache hit for {ticker} — returning cached analysis")
        cached = get_latest_analysis(ticker)
        if cached:
            cached["from_cache"] = True
            return cached

    logger.info(f"Cache miss for {ticker} — running full agent analysis")

    # ── Step 2: Get forecast data separately ─────────────────────
    # We fetch the Prophet forecast data directly (not through the agent)
    # so we have the structured dict for the chart in Streamlit.
    # The PredictorAgent will also run the forecast internally
    # but returns text — we need the raw dict for chart rendering.
    logger.info(f"Running Prophet forecast for {ticker}...")
    prophet_tool = ProphetForecasterTool()
    forecast_data = prophet_tool._run(ticker)

    # Also get company name for better news search
    yf_tool = YFinanceTool()
    yf_data = yf_tool._run(ticker)
    company_name = yf_data.get("company_name", "")

    # ── Step 3: Run agents 1-4 in parallel ───────────────────────
    # Using ThreadPoolExecutor to run all 4 agents simultaneously.
    # Without parallelism, 4 agents × ~20 seconds each = 80 seconds.
    # With parallelism, all 4 run at once = ~20 seconds total.
    #
    # Each agent makes API calls (Groq LLM + data tools) which are
    # I/O-bound — perfect for thread parallelism.
    logger.info(f"Running 4 specialist agents in parallel for {ticker}...")

    # Create all agents and tasks
    news_agent = create_news_agent()
    news_task = create_news_task(news_agent, ticker, company_name)

    financials_agent = create_financials_agent()
    financials_task = create_financials_task(financials_agent, ticker)

    sentiment_agent = create_sentiment_agent()
    sentiment_task = create_sentiment_task(sentiment_agent, ticker)

    predictor_agent = create_predictor_agent()
    predictor_task = create_predictor_task(predictor_agent, ticker)

    # Map of task name to (agent, task) pair for parallel execution
    agent_tasks = {
        "news": (news_agent, news_task),
        "financials": (financials_agent, financials_task),
        "sentiment": (sentiment_agent, sentiment_task),
        "predictor": (predictor_agent, predictor_task),
    }

    # Results dict — populated as each agent finishes
    results = {}

    # Run all 4 agents concurrently
    # max_workers=4 means up to 4 threads run simultaneously
    with ThreadPoolExecutor(max_workers=4) as executor:
        # Submit all tasks to the thread pool
        import time

        future_to_name = {}
        for i, (name, (agent, task)) in enumerate(agent_tasks.items()):
        # Stagger agent starts by 3 seconds each
        # Prevents all 4 agents hitting Groq token limit simultaneously
            if i > 0:
                time.sleep(3)
            future = executor.submit(run_single_agent_task, agent, task)
            future_to_name[future] = name

        # Collect results as each agent completes
        # as_completed() yields futures in the order they finish
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                results[name] = future.result()
                logger.info(f"Agent '{name}' completed for {ticker}")
            except Exception as e:
                # If an agent fails, store an error message
                # The CriticAgent will note the missing data
                logger.error(f"Agent '{name}' failed for {ticker}: {e}")
                results[name] = f"Analysis unavailable due to error: {str(e)}"

    # ── Step 4: Run CriticAgent ───────────────────────────────────
    # CriticAgent receives all 4 outputs and produces the final verdict.
    # It runs sequentially AFTER all 4 parallel agents complete.
    logger.info(f"Running CriticAgent for {ticker}...")

    critic_agent = create_critic_agent()
    critic_task = create_critic_task(
        agent=critic_agent,
        ticker=ticker,
        news_output=results.get("news", "Unavailable"),
        financials_output=results.get("financials", "Unavailable"),
        sentiment_output=results.get("sentiment", "Unavailable"),
        predictor_output=results.get("predictor", "Unavailable"),
    )

    critic_output = run_single_agent_task(critic_agent, critic_task)
    logger.info(f"CriticAgent completed for {ticker}")

    # ── Step 5: Build final report ────────────────────────────────
    writer = ReportWriter()
    report = writer.build_report(
        ticker=ticker,
        news_output=results.get("news", "Unavailable"),
        financials_output=results.get("financials", "Unavailable"),
        sentiment_output=results.get("sentiment", "Unavailable"),
        predictor_output=results.get("predictor", "Unavailable"),
        critic_output=critic_output,
        forecast_data=forecast_data,
    )

    # Mark as freshly generated (not from cache)
    report["from_cache"] = False

    # ── Step 6: Save to DynamoDB ──────────────────────────────────
    # Store for caching — next request for this ticker within 30 min
    # will return this result instantly
    save_analysis(ticker, report)
    logger.info(f"Analysis saved to DynamoDB for {ticker}")

    return report


# ── CLI entry point ───────────────────────────────────────────────
# Allows running the crew directly from terminal:
#   python3 -m backend.crew.equityiq_crew AAPL
#
# This is how you test the full pipeline during development
# before the FastAPI layer is built.
if __name__ == "__main__":
    # Get ticker from command line argument
    # Default to AAPL if none provided
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

    print(f"\nRunning EquityIQ analysis for {ticker}...")
    print("This takes 30-60 seconds — agents are working...\n")

    report = analyze_ticker(ticker)

    # Print formatted report to terminal
    writer = ReportWriter()
    print(writer.format_for_display(report))