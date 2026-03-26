# backend/tools/yfinance_tool.py
#
# This tool fetches real stock data from Yahoo Finance.
# It is called by the FinancialsAgent during crew execution.
#
# yfinance is completely free — no API key needed.
# It scrapes Yahoo Finance's backend the same way your browser would.
#
# What this tool returns:
#   - Current price and daily % change
#   - Fundamental ratios: P/E, EPS, revenue growth, profit margin
#   - Balance sheet health: debt/equity, current ratio
#   - Analyst consensus: buy/hold/sell + 12-month price target
#   - 2 years of daily closing prices (used later by Prophet)

import yfinance as yf
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
import logging

# Standard Python logger — prints to terminal during development
logger = logging.getLogger(__name__)


# ── Input Schema ─────────────────────────────────────────────────
# CrewAI uses this to validate what the agent passes to the tool.
# If the agent passes something other than a string ticker,
# Pydantic raises a clear error before the tool even runs.
class YFinanceInput(BaseModel):
    ticker: str = Field(
        description="Stock ticker symbol, e.g. 'NVDA', 'AAPL', 'MSFT'"
    )


# ── The Tool ─────────────────────────────────────────────────────
class YFinanceTool(BaseTool):
    """
    Fetches comprehensive financial data for a stock ticker.
    CrewAI agents call this tool by name during their execution.
    """

    # These two fields are required by CrewAI.
    # 'name' is how the agent refers to this tool in its reasoning.
    # 'description' tells the agent WHEN to use this tool.
    name: str = "YFinanceTool"
    description: str = (
        "Fetches real-time stock price, P/E ratio, EPS, revenue growth, "
        "analyst ratings, price target, and 2-year price history "
        "for a given stock ticker symbol."
    )
    args_schema: type[BaseModel] = YFinanceInput

    def _run(self, ticker: str) -> dict:
        """
        Main method CrewAI calls when an agent uses this tool.
        Always returns a dict — CrewAI converts it to text for
        the agent's context window automatically.
        """
        # Normalize ticker: remove spaces, force uppercase
        # So 'nvda', ' NVDA ', 'Nvda' all work correctly
        ticker = ticker.upper().strip()
        logger.info(f"YFinanceTool called for {ticker}")

        try:
            # yf.Ticker creates a handle to Yahoo Finance for this stock
            stock = yf.Ticker(ticker)

            # .info is a large dictionary of company metadata.
            # We extract only the fields our agents actually need.
            info = stock.info

            # ── Price ─────────────────────────────────────────────
            current_price = (
                info.get("currentPrice") or
                info.get("regularMarketPrice")  # fallback field name
            )
            prev_close = info.get("previousClose")

            # Calculate how much the stock moved today in percentage
            daily_change_pct = None
            if current_price and prev_close:
                daily_change_pct = round(
                    ((current_price - prev_close) / prev_close) * 100, 2
                )

            # ── Valuation ratios ──────────────────────────────────
            # P/E ratio = price / earnings per share
            # High P/E means market expects high future growth
            # trailingPE = based on last 12 months actual earnings
            # forwardPE  = based on next 12 months estimated earnings
            pe_ratio = info.get("trailingPE") or info.get("forwardPE")

            # EPS = earnings per share (trailing 12 months)
            # Positive = profitable, Negative = losing money
            eps = info.get("trailingEps")

            # Revenue growth year-over-year as a decimal
            # 0.15 means +15% growth — we convert to percentage
            revenue_growth = info.get("revenueGrowth")
            if revenue_growth is not None:
                revenue_growth = round(revenue_growth * 100, 1)

            # Profit margin as decimal — convert to percentage
            # 0.25 means the company keeps $0.25 of every $1 in revenue
            profit_margin = info.get("profitMargins")
            if profit_margin is not None:
                profit_margin = round(profit_margin * 100, 1)

            # ── Balance sheet health ──────────────────────────────
            # Debt/equity: how much debt relative to equity
            # Lower is safer — above 2.0 is considered high risk
            debt_to_equity = info.get("debtToEquity")

            # Current ratio: current assets / current liabilities
            # Above 1.0 means company can pay its short-term bills
            current_ratio = info.get("currentRatio")

            # ── Analyst consensus ─────────────────────────────────
            # recommendationKey: "strong_buy", "buy", "hold", "sell"
            # targetMeanPrice: average analyst 12-month price target
            rec_key = info.get("recommendationKey", "N/A")
            target_price = info.get("targetMeanPrice")

            # How much upside/downside to analyst target in percentage
            upside_pct = None
            if target_price and current_price:
                upside_pct = round(
                    ((target_price - current_price) / current_price) * 100, 1
                )

            # ── 52-week range ─────────────────────────────────────
            # Tells us where current price sits in the yearly range
            week52_high = info.get("fiftyTwoWeekHigh")
            week52_low = info.get("fiftyTwoWeekLow")

            # ── Historical prices ─────────────────────────────────
            # Fetch 2 years of daily closing prices.
            # This data is passed to Prophet in the forecasting step.
            history = stock.history(period="2y")
            price_history = []
            if not history.empty:
                price_history = [
                    {
                        "date": str(idx.date()),
                        "close": round(float(row["Close"]), 2)
                    }
                    for idx, row in history.iterrows()
                ]

            # ── Build result dict ─────────────────────────────────
            # This entire dict becomes the agent's context for
            # the FinancialsAgent's analysis step
            result = {
                "ticker": ticker,
                "company_name": info.get("longName", ticker),
                "sector": info.get("sector", "N/A"),
                "industry": info.get("industry", "N/A"),
                # Price info
                "current_price": current_price,
                "daily_change_pct": daily_change_pct,
                "week52_high": week52_high,
                "week52_low": week52_low,
                "market_cap_billions": round(
                    info.get("marketCap", 0) / 1e9, 1
                ) if info.get("marketCap") else None,
                # Fundamentals
                "pe_ratio": round(pe_ratio, 1) if pe_ratio else None,
                "eps_ttm": round(eps, 2) if eps else None,
                "revenue_growth_pct": revenue_growth,
                "profit_margin_pct": profit_margin,
                # Balance sheet
                "debt_to_equity": round(debt_to_equity, 1) if debt_to_equity else None,
                "current_ratio": round(current_ratio, 2) if current_ratio else None,
                # Analyst view
                "analyst_recommendation": rec_key,
                "analyst_target_price": target_price,
                "upside_to_target_pct": upside_pct,
                # 2yr history for Prophet forecaster
                "price_history": price_history,
                "data_available": True,
            }

            logger.info(f"YFinanceTool success: {ticker} @ ${current_price}")
            return result

        except Exception as e:
            # Return structured error so the agent handles it gracefully
            # instead of the entire crew crashing
            logger.error(f"YFinanceTool error for {ticker}: {e}")
            return {
                "ticker": ticker,
                "error": str(e),
                "data_available": False
            }