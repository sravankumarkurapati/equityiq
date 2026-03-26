# backend/tools/alpha_vantage_tool.py
#
# Fetches two things from Alpha Vantage:
#
# 1. NEWS SENTIMENT
#    Alpha Vantage scans 50+ financial news sources
#    (Bloomberg, Reuters, WSJ, MarketWatch, Seeking Alpha etc.)
#    and returns a sentiment score for each article:
#      score > 0.35  = Bullish
#      score < -0.35 = Bearish
#      in between    = Neutral
#    This is more reliable than scraping Reddit because these
#    are professional financial journalists, not retail traders.
#
# 2. TECHNICAL INDICATORS
#    RSI  — Relative Strength Index
#          Measures momentum. Above 70 = overbought, below 30 = oversold.
#    MACD — Moving Average Convergence Divergence
#          Measures trend direction and momentum shifts.
#
# Alpha Vantage free tier = 25 requests/day
# We make 3 requests per ticker call (news + RSI + MACD)
# So we can analyze ~8 tickers per day on free tier.

import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
import logging
import time

from backend.config import settings

logger = logging.getLogger(__name__)

# Base URL for all Alpha Vantage API calls
AV_BASE_URL = "https://www.alphavantage.co/query"


class AlphaVantageInput(BaseModel):
    ticker: str = Field(
        description="Stock ticker symbol, e.g. 'NVDA'"
    )


class AlphaVantageTool(BaseTool):
    """
    Fetches professional news sentiment scores and technical
    indicators (RSI, MACD) for a stock from Alpha Vantage.
    Used by the SentimentAgent.
    """

    name: str = "AlphaVantageTool"
    description: str = (
        "Fetches professional news sentiment scores from 50+ financial "
        "news sources, plus RSI and MACD technical indicators. "
        "Returns overall sentiment (Bullish/Bearish/Neutral) with scores."
    )
    args_schema: type[BaseModel] = AlphaVantageInput

    def _run(self, ticker: str) -> dict:
        """
        Makes 3 API calls:
          1. News sentiment for this ticker
          2. RSI (14-day)
          3. MACD
        Combines results into one dict for the SentimentAgent.
        """
        ticker = ticker.upper().strip()
        logger.info(f"AlphaVantageTool called for {ticker}")

        try:
            # Fetch all three data points
            sentiment = self._get_news_sentiment(ticker)
            rsi = self._get_rsi(ticker)
            macd = self._get_macd(ticker)

            # ── Combine into overall signal ───────────────────────
            # Count how many indicators are bullish vs bearish
            # to produce a combined signal the agent can reason about
            bullish_count = 0
            bearish_count = 0

            if sentiment.get("overall_sentiment") == "Bullish":
                bullish_count += 1
            elif sentiment.get("overall_sentiment") == "Bearish":
                bearish_count += 1

            # RSI interpretation
            rsi_value = rsi.get("current_rsi")
            rsi_signal = "Neutral"
            if rsi_value:
                if rsi_value < 30:
                    # Oversold — potential buy opportunity
                    rsi_signal = "Bullish"
                    bullish_count += 1
                elif rsi_value > 70:
                    # Overbought — potential sell signal
                    rsi_signal = "Bearish"
                    bearish_count += 1
                else:
                    rsi_signal = "Neutral"

            # MACD interpretation
            macd_signal = macd.get("signal", "Neutral")
            if macd_signal == "Bullish":
                bullish_count += 1
            elif macd_signal == "Bearish":
                bearish_count += 1

            # Overall combined signal
            if bullish_count > bearish_count:
                combined_signal = "Bullish"
            elif bearish_count > bullish_count:
                combined_signal = "Bearish"
            else:
                combined_signal = "Neutral"

            result = {
                "ticker": ticker,
                # News sentiment from professional sources
                "news_sentiment": sentiment,
                # Technical indicators
                "rsi": {
                    "value": rsi_value,
                    "signal": rsi_signal,
                    "interpretation": rsi.get("interpretation", ""),
                },
                "macd": macd,
                # Combined signal across all three
                "combined_signal": combined_signal,
                "bullish_indicators": bullish_count,
                "bearish_indicators": bearish_count,
                "data_available": True,
            }

            logger.info(
                f"AlphaVantageTool success: {ticker} "
                f"signal={combined_signal}"
            )
            return result

        except Exception as e:
            logger.error(f"AlphaVantageTool error for {ticker}: {e}")
            return {
                "ticker": ticker,
                "error": str(e),
                "data_available": False
            }

    def _get_news_sentiment(self, ticker: str) -> dict:
        """
        Calls Alpha Vantage NEWS_SENTIMENT endpoint.

        Returns sentiment scored by their NLP model across
        articles from Bloomberg, Reuters, WSJ, and 47 other sources.

        Each article gets a score:
          0.35 to 1.0   = Bullish
          -0.35 to 0.35 = Neutral
          -1.0 to -0.35 = Bearish
        """
        params = {
            "function": "NEWS_SENTIMENT",
            "tickers": ticker,
            "limit": 20,               # analyze last 20 articles
            "apikey": settings.alpha_vantage_key,
        }

        # Respect Alpha Vantage rate limit (5 requests/minute on free tier)
        time.sleep(0.5)

        resp = requests.get(AV_BASE_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # Handle API error responses
        if "Information" in data:
            # This message appears when you hit the rate/daily limit
            logger.warning(f"Alpha Vantage limit reached: {data['Information']}")
            return {
                "overall_sentiment": "Unknown",
                "error": "API limit reached",
                "articles_analyzed": 0
            }

        articles = data.get("feed", [])
        if not articles:
            return {
                "overall_sentiment": "Neutral",
                "articles_analyzed": 0,
                "average_score": 0.0
            }

        # Extract sentiment scores for our specific ticker from each article
        # Each article has sentiment for multiple tickers — we only want ours
        scores = []
        relevant_articles = []

        for article in articles:
            # ticker_sentiment is a list of {ticker, relevance_score, sentiment_score}
            for ts in article.get("ticker_sentiment", []):
                if ts.get("ticker") == ticker:
                    try:
                        score = float(ts.get("ticker_sentiment_score", 0))
                        scores.append(score)

                        # Keep top articles for the agent to read
                        if len(relevant_articles) < 5:
                            relevant_articles.append({
                                "title": article.get("title", ""),
                                "source": article.get("source", ""),
                                "date": article.get("time_published", "")[:8],
                                "sentiment_score": round(score, 3),
                                "sentiment_label": ts.get(
                                    "ticker_sentiment_label", "Neutral"
                                ),
                            })
                    except (ValueError, TypeError):
                        continue

        if not scores:
            return {
                "overall_sentiment": "Neutral",
                "articles_analyzed": 0,
                "average_score": 0.0
            }

        avg_score = sum(scores) / len(scores)

        # Classify overall sentiment based on average score
        if avg_score >= 0.35:
            overall = "Bullish"
        elif avg_score <= -0.35:
            overall = "Bearish"
        else:
            overall = "Neutral"

        return {
            "overall_sentiment": overall,
            "average_score": round(avg_score, 3),
            "articles_analyzed": len(scores),
            "top_articles": relevant_articles,
        }

    def _get_rsi(self, ticker: str) -> dict:
        """
        Fetches RSI (Relative Strength Index) — 14-day period.

        RSI measures how fast a stock is moving up or down.
        Range is 0 to 100:
          > 70 = overbought (price may pull back soon)
          < 30 = oversold   (price may bounce soon)
          30-70 = normal range

        We use the most recent daily RSI value.
        """
        params = {
            "function": "RSI",
            "symbol": ticker,
            "interval": "daily",
            "time_period": 14,          # standard 14-day RSI
            "series_type": "close",     # calculate from closing prices
            "apikey": settings.alpha_vantage_key,
        }

        time.sleep(0.5)

        resp = requests.get(AV_BASE_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if "Information" in data or "Technical Analysis: RSI" not in data:
            logger.warning(f"RSI unavailable for {ticker} — likely daily limit reached")
            return {
                "current_rsi": None,
                "signal": "Neutral",
                "interpretation": "Daily API limit reached — using Prophet RSI instead"
            }

        # Get the most recent RSI value
        # The dict keys are dates — sorted descending, first = most recent
        rsi_data = data["Technical Analysis: RSI"]
        latest_date = sorted(rsi_data.keys(), reverse=True)[0]
        latest_rsi = float(rsi_data[latest_date]["RSI"])

        # Human-readable interpretation
        if latest_rsi > 70:
            interpretation = f"Overbought at {latest_rsi:.1f} — price may face resistance"
        elif latest_rsi < 30:
            interpretation = f"Oversold at {latest_rsi:.1f} — potential bounce opportunity"
        else:
            interpretation = f"Neutral at {latest_rsi:.1f} — normal trading range"

        return {
            "current_rsi": round(latest_rsi, 1),
            "as_of_date": latest_date,
            "interpretation": interpretation,
        }

    def _get_macd(self, ticker: str) -> dict:
        """
        Fetches MACD (Moving Average Convergence Divergence).

        MACD shows the relationship between two moving averages:
          Fast EMA (12-day) minus Slow EMA (26-day) = MACD Line
          9-day EMA of MACD Line = Signal Line

        Interpretation:
          MACD crosses above Signal Line = Bullish (buy signal)
          MACD crosses below Signal Line = Bearish (sell signal)
          MACD above zero = upward momentum
          MACD below zero = downward momentum
        """
        params = {
            "function": "MACD",
            "symbol": ticker,
            "interval": "daily",
            "series_type": "close",
            "apikey": settings.alpha_vantage_key,
        }

        time.sleep(0.5)

        resp = requests.get(AV_BASE_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if "Information" in data or "Technical Analysis: MACD" not in data:
            return {
                "signal": "Neutral",
                "interpretation": "Daily API limit reached — using Prophet MACD instead"
            }

        macd_data = data["Technical Analysis: MACD"]
        latest_date = sorted(macd_data.keys(), reverse=True)[0]
        latest = macd_data[latest_date]

        macd_value = float(latest["MACD"])
        signal_value = float(latest["MACD_Signal"])
        histogram = float(latest["MACD_Hist"])

        # MACD above signal line = bullish momentum
        if macd_value > signal_value:
            signal = "Bullish"
            interpretation = "MACD above signal line — upward momentum"
        else:
            signal = "Bearish"
            interpretation = "MACD below signal line — downward momentum"

        return {
            "macd_value": round(macd_value, 4),
            "signal_line": round(signal_value, 4),
            "histogram": round(histogram, 4),
            "signal": signal,
            "interpretation": interpretation,
            "as_of_date": latest_date,
        }