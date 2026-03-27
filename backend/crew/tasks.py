# backend/crew/tasks.py
#
# Central place for any shared task configuration.
# Currently holds the daily screener task used by Lambda.
#
# Why separate from equityiq_crew.py:
#   The Lambda screener (runs every morning at 8:30 AM)
#   uses a lighter version of the analysis — no sentiment,
#   no full critic pass. Just financials + forecast.
#   Keeping it here avoids duplicating logic.

from crewai import Task
from crewai import Agent


def create_screener_task(agent: Agent, tickers: list[str]) -> Task:
    """
    Lightweight task for the daily screener Lambda.
    Analyzes multiple tickers quickly to pick the top 5.

    This is faster than full analysis because:
      - No news fetching (saves NewsAPI quota)
      - No sentiment analysis (saves Alpha Vantage quota)
      - Just fundamentals + Prophet forecast
      - LLM ranks and picks top 5

    Args:
        agent: The screener agent
        tickers: List of ticker symbols to screen e.g. ["AAPL", "NVDA", ...]
    """

    tickers_str = ", ".join(tickers)

    task = Task(
        description=(
            f"Screen these stocks and identify the top 5 to watch today: "
            f"{tickers_str}\n\n"
            f"For each ticker evaluate:\n"
            f"1. Analyst consensus (buy/hold/sell)\n"
            f"2. Upside to analyst price target\n"
            f"3. Prophet 7-day forecast direction and confidence\n"
            f"4. Recent momentum (accelerating/stable/declining)\n"
            f"5. P/E ratio vs sector average\n\n"
            f"Rank all tickers and select the top 5 with the strongest "
            f"combination of analyst support + positive forecast + "
            f"reasonable valuation.\n"
            f"For each pick provide: ticker, current price, "
            f"predicted 7d price, analyst rating, and one sentence rationale."
        ),

        expected_output=(
            "Top 5 stock picks in this exact format for each:\n"
            "PICK_1: [TICKER] | Price: $X | Target: $X | "
            "Analyst: [rating] | Rationale: [one sentence]\n"
            "PICK_2: ...\n"
            "PICK_3: ...\n"
            "PICK_4: ...\n"
            "PICK_5: ...\n"
            "SCREEN_SUMMARY: [2 sentences on overall market conditions today]"
        ),

        agent=agent,
    )

    return task