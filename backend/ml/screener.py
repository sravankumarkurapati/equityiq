# backend/ml/screener.py
#
# Real-time market screener that fetches TODAY'S most active
# stocks from Yahoo Finance — no hardcoded tickers.
#
# Data sources:
#   - Yahoo Finance most active (real-time volume leaders)
#   - Yahoo Finance top gainers (momentum stocks)
#   - Yahoo Finance top losers (contrarian opportunities)
#
# Scoring (100 points):
#   - Analyst recommendation : 40 pts
#   - Upside to price target  : 30 pts
#   - Prophet forecast        : 20 pts
#   - Forecast confidence     : 10 pts

import os
from dotenv import load_dotenv
load_dotenv()
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY", "")

import logging
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime, timezone
from backend.tools.yfinance_tool import YFinanceTool
from backend.ml.prophet_forecaster import ProphetForecasterTool
from backend.db.dynamo_client import save_daily_picks

logger = logging.getLogger(__name__)


def get_market_movers() -> list[str]:
    """
    Fetches TODAY's most active, top gaining stocks
    from Yahoo Finance screeners.
    Returns a deduplicated list of tickers.
    """
    tickers = set()

    # Yahoo Finance screener URLs
    screener_urls = {
        "most_active": "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=most_actives&count=25",
        "day_gainers": "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=day_gainers&count=25",
        "growth_technology": "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=growth_technology_stocks&count=15",
        "undervalued_large": "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=undervalued_large_caps&count=15",
    }

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }

    for name, url in screener_urls.items():
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            # Extract tickers from response
            quotes = (
                data.get("finance", {})
                    .get("result", [{}])[0]
                    .get("quotes", [])
            )

            for quote in quotes:
                symbol = quote.get("symbol", "")
                # Filter out non-US stocks, ETFs with dots, warrants
                if (symbol and
                    "." not in symbol and
                    "-" not in symbol and
                    len(symbol) <= 5):
                    tickers.add(symbol)

            logger.info(f"Got {len(quotes)} tickers from {name}")

        except Exception as e:
            logger.warning(f"Failed to fetch {name}: {e}")
            continue

    # Fallback if all screeners fail
    if len(tickers) < 10:
        logger.warning("Screeners failed — using fallback top 20 by volume")
        fallback = [
            "AAPL", "MSFT", "NVDA", "TSLA", "AMZN",
            "META", "GOOGL", "AMD", "PLTR", "SOFI",
            "BAC", "F", "INTC", "T", "AAL",
            "RIVN", "NIO", "LCID", "GME", "AMC",
        ]
        tickers.update(fallback)

    result = list(tickers)
    logger.info(f"Total tickers to screen: {len(result)}")
    return result


def get_realtime_price_change(ticker: str) -> float | None:
    """
    Gets today's price change percentage for a ticker.
    Used as an additional momentum signal.
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        current = info.get("currentPrice") or info.get("regularMarketPrice")
        prev_close = info.get("previousClose")
        if current and prev_close:
            return round(((current - prev_close) / prev_close) * 100, 2)
    except Exception:
        pass
    return None


def score_stock(yf_data: dict, forecast: dict) -> float:
    """
    Scores a stock 0-100 based on analyst + forecast signals.
    """
    score = 0.0

    # ── Analyst recommendation (40 pts) ──────────────────────────
    rec = str(yf_data.get("analyst_recommendation", "")).lower()
    if "strong_buy" in rec or "strongbuy" in rec:
        score += 40
    elif rec == "buy":
        score += 30
    elif rec == "hold":
        score += 10

    # ── Upside to analyst target (30 pts) ────────────────────────
    upside = yf_data.get("upside_to_target_pct")
    if upside is not None:
        if upside >= 20:
            score += 30
        elif upside >= 10:
            score += 20
        elif upside >= 5:
            score += 10
        elif upside > 0:
            score += 5

    # ── Prophet direction (20 pts) ────────────────────────────────
    direction = str(forecast.get("direction_signal", "NEUTRAL"))
    if direction == "BULLISH":
        score += 20
    elif direction == "NEUTRAL":
        score += 5

    # ── Forecast confidence (10 pts) ─────────────────────────────
    conf = forecast.get("confidence_score", 0)
    if conf >= 90:
        score += 10
    elif conf >= 80:
        score += 7
    elif conf >= 70:
        score += 5

    return round(score, 1)


def run_screener(top_n: int = 5) -> list[dict]:
    """
    Fetches today's market movers, scores each one,
    and returns the top N picks.
    """

    # Get today's real market movers
    universe = get_market_movers()
    logger.info(f"Screening {len(universe)} real market movers...")

    yf_tool = YFinanceTool()
    prophet_tool = ProphetForecasterTool()
    scored = []

    for ticker in universe:
        try:
            # Fetch fundamentals
            yf_data = yf_tool._run(ticker)
            if not yf_data.get("current_price"):
                continue

            # Skip stocks under $5 (penny stocks — too volatile)
            price = yf_data.get("current_price", 0)
            if price < 5:
                continue

            # Skip stocks with no analyst coverage
            if not yf_data.get("analyst_recommendation"):
                continue

            # Run Prophet forecast
            forecast = prophet_tool._run(ticker)
            if not forecast.get("data_available", True):
                continue

            # Score it
            score = score_stock(yf_data, forecast)
            if score < 25:
                continue

            # Get today's actual price movement
            today_change = get_realtime_price_change(ticker)

            # Build rationale
            direction = forecast.get("direction_signal", "NEUTRAL")
            conf = forecast.get("confidence_score", 0)
            rec = str(yf_data.get("analyst_recommendation", "N/A")).upper()
            upside = yf_data.get("upside_to_target_pct")
            change_7d = forecast.get("predicted_change_pct", 0)
            sector = yf_data.get("sector", "N/A")
            company = yf_data.get("company_name", ticker)

            upside_str = (
                f" Target upside: {upside:+.1f}%."
                if upside is not None else ""
            )
            today_str = (
                f" Today: {today_change:+.1f}%."
                if today_change is not None else ""
            )

            rationale = (
                f"{company} ({sector}). "
                f"Score: {score}/100. "
                f"Analyst: {rec}.{upside_str}{today_str} "
                f"7-day forecast: {direction} "
                f"({change_7d:+.1f}%) "
                f"at {conf:.0f}% confidence."
            )

            scored.append({
                "ticker": ticker,
                "score": score,
                "company_name": company,
                "sector": sector,
                "current_price": yf_data.get("current_price"),
                "predicted_price_7d": forecast.get("predicted_price_7d"),
                "predicted_change_pct": change_7d,
                "today_change_pct": today_change,
                "direction": direction,
                "analyst_recommendation": yf_data.get(
                    "analyst_recommendation", "N/A"
                ),
                "upside_to_target_pct": upside,
                "confidence_score": conf,
                "rationale": rationale,
            })

            logger.info(
                f"{ticker}: score={score} "
                f"direction={direction} "
                f"rec={rec}"
            )

        except Exception as e:
            logger.warning(f"Skipping {ticker}: {e}")
            continue

    # Sort by score and return top N
    scored.sort(key=lambda x: x["score"], reverse=True)
    top_picks = scored[:top_n]

    logger.info(
        f"Top {len(top_picks)} picks: "
        f"{[p['ticker'] for p in top_picks]}"
    )

    return top_picks


def run_and_save_daily_picks() -> bool:
    """
    Runs screener and saves to DynamoDB.
    Called by Lambda at 8:30 AM ET and manually for testing.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    logger.info(f"Running daily screener for {today}...")

    picks = run_screener(top_n=5)

    if not picks:
        logger.error("No picks generated")
        return False

    saved = save_daily_picks(today, picks)

    if saved:
        print(f"\nTop 5 picks for {today}:")
        for i, p in enumerate(picks):
            print(
                f"  #{i+1} {p['ticker']} "
                f"({p.get('company_name', '')}) "
                f"score={p['score']} "
                f"direction={p['direction']} "
                f"7d={p.get('predicted_change_pct', 0):+.1f}%"
            )

    return saved


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("\nEquityIQ Real-Time Market Screener")
    print("Fetching today's market movers from Yahoo Finance...")
    print("This takes 5-8 minutes (Prophet fits each stock)\n")
    run_and_save_daily_picks()