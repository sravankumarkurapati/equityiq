# backend/tools/news_tool.py
#
# Fetches recent news articles about a stock from NewsAPI.
#
# Why news matters for stock analysis:
#   - Earnings surprises, product launches, lawsuits, CEO changes
#     all move stock prices significantly
#   - News from the past 7 days gives the agent context that
#     pure financial numbers cannot provide
#
# NewsAPI free tier:
#   - 100 requests per day
#   - Articles up to 30 days old
#   - Returns headline + description + source + URL
#
# The NewsAgent uses this tool then asks the LLM to:
#   1. Summarize the most important stories
#   2. Identify if news sentiment is positive/negative/neutral
#   3. Flag any major risk events (lawsuits, recalls, investigations)

import requests
from datetime import datetime, timedelta
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
import logging
import time

from backend.config import settings

logger = logging.getLogger(__name__)

# NewsAPI endpoint for searching articles
NEWSAPI_URL = "https://newsapi.org/v2/everything"


class NewsInput(BaseModel):
    ticker: str = Field(
        description="Stock ticker symbol, e.g. 'AAPL'"
    )
    company_name: str = Field(
        default="",
        description="Full company name for better search results, e.g. 'Apple'"
    )
    days_back: int = Field(
        default=7,
        description="How many days of news to fetch. Max 30 on free tier."
    )


class NewsTool(BaseTool):
    """
    Fetches recent news articles about a company from NewsAPI.
    Returns up to 10 articles with title, source, date, and summary.
    """

    name: str = "NewsTool"
    description: str = (
        "Fetches recent news articles about a stock from the past 7 days. "
        "Returns headlines, sources, publication dates, and article summaries."
    )
    args_schema: type[BaseModel] = NewsInput

    def _run(
        self,
        ticker: str,
        company_name: str = "",
        days_back: int = 7
    ) -> dict:
        """
        Fetches news articles and returns them structured for the agent.
        The NewsAgent's LLM will analyze these articles for sentiment
        and key events after receiving this data.
        """
        ticker = ticker.upper().strip()
        logger.info(f"NewsTool called for {ticker}")

        # Build search query
        # Using both ticker and company name catches more articles
        # e.g. "Apple" OR "AAPL" finds more than just "AAPL"
        if company_name:
            # Quote the company name to search as exact phrase
            query = f'"{company_name}" OR "{ticker}" stock'
        else:
            query = f'"{ticker}" stock market'

        # Calculate date range
        # NewsAPI free tier only goes back 30 days maximum
        to_date = datetime.now()
        from_date = to_date - timedelta(days=min(days_back, 30))

        # These are the parameters NewsAPI expects
        params = {
            "q": query,
            "from": from_date.strftime("%Y-%m-%d"),
            "to": to_date.strftime("%Y-%m-%d"),
            "language": "en",           # English articles only
            "sortBy": "relevancy",      # Most relevant first, not just newest
            "pageSize": 10,             # Fetch 10 articles max
            "apiKey": settings.news_api_key,
        }

        try:
            # Small delay to avoid hitting rate limits
            time.sleep(0.2)

            resp = requests.get(
                NEWSAPI_URL,
                params=params,
                timeout=15
            )

            # Handle common error cases clearly
            if resp.status_code == 401:
                return {
                    "ticker": ticker,
                    "error": "Invalid NewsAPI key — check NEWS_API_KEY in .env",
                    "articles": [],
                    "data_available": False
                }

            if resp.status_code == 429:
                return {
                    "ticker": ticker,
                    "error": "NewsAPI rate limit reached (100/day on free tier)",
                    "articles": [],
                    "data_available": False
                }

            resp.raise_for_status()
            data = resp.json()

            if data.get("status") != "ok":
                return {
                    "ticker": ticker,
                    "error": f"NewsAPI error: {data.get('message', 'unknown')}",
                    "articles": [],
                    "data_available": False
                }

            raw_articles = data.get("articles", [])

            # Format each article into a clean structure for the agent
            # We strip down the raw NewsAPI response to only what matters
            formatted_articles = []
            for article in raw_articles:

                # Skip articles with no title or removed articles
                title = article.get("title", "")
                if not title or title == "[Removed]":
                    continue

                formatted_articles.append({
                    # The headline — most important field for sentiment
                    "title": title,

                    # Where the article came from
                    "source": article.get("source", {}).get("name", "Unknown"),

                    # Date only (no time) — easier for the agent to reason about
                    "published_date": article.get("publishedAt", "")[:10],

                    # 1-2 sentence preview of the article content
                    # 'description' is the subtitle/preview text
                    # Fall back to first 300 chars of content if no description
                    "summary": (
                        article.get("description") or
                        (article.get("content") or "")[:300]
                    ),

                    # Direct link — included in the final report
                    "url": article.get("url", ""),
                })

            result = {
                "ticker": ticker,
                "query_used": query,
                "date_range": (
                    f"{from_date.strftime('%Y-%m-%d')} "
                    f"to {to_date.strftime('%Y-%m-%d')}"
                ),
                "articles_found": len(formatted_articles),
                "articles": formatted_articles,
                "data_available": True,
            }

            logger.info(f"NewsTool success: {len(formatted_articles)} articles for {ticker}")
            return result

        except Exception as e:
            logger.error(f"NewsTool error for {ticker}: {e}")
            return {
                "ticker": ticker,
                "error": str(e),
                "articles": [],
                "data_available": False
            }