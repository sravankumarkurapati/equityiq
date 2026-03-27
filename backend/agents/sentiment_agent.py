# backend/agents/sentiment_agent.py
#
# The SentimentAgent measures market mood around a stock.
#
# It uses AlphaVantageTool which gives:
#   - News sentiment scored by NLP across 50+ professional sources
#   - RSI (overbought/oversold signal)
#   - MACD (momentum direction signal)
#
# Why sentiment matters:
#   Even fundamentally strong stocks can drop if sentiment turns
#   negative (fear, panic selling, negative press cycles).
#   And weak stocks can rally on positive sentiment alone.
#   Sentiment captures what pure financial numbers miss.
#
# The agent combines all three signals into one clear verdict:
#   BULLISH / BEARISH / NEUTRAL / MIXED
from dotenv import load_dotenv
load_dotenv()

from crewai import Agent, Task, LLM

from backend.tools.alpha_vantage_tool import AlphaVantageTool
from backend.config import settings


def create_sentiment_agent() -> Agent:
    """
    Creates the SentimentAgent.
    Uses AlphaVantageTool for professional sentiment + technicals.
    """

    llm = LLM(
        model="groq/llama-3.3-70b-versatile",
        temperature=0.1,
    )

    av_tool = AlphaVantageTool()

    agent = Agent(
        role="Market Sentiment Analyst",

        goal=(
            "Measure overall market sentiment for a stock by analyzing "
            "professional news sentiment scores and technical momentum "
            "indicators. Determine if the market mood is bullish, "
            "bearish, neutral, or mixed."
        ),

        backstory=(
            "You are a quantitative sentiment analyst who spent 10 years "
            "at a hedge fund building sentiment models. You understand that "
            "markets are driven by both fundamentals and psychology. "
            "You know how to read RSI and MACD signals without over-indexing "
            "on any single indicator. You always contextualize technical "
            "signals — an RSI of 72 is less alarming in a strong uptrend "
            "than in a sideways market. You are skeptical of extreme readings "
            "and always look for confirmation across multiple signals."
        ),

        tools=[av_tool],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=3,
    )

    return agent


def create_sentiment_task(agent: Agent, ticker: str) -> Task:
    """
    Creates the Task for the SentimentAgent.
    """

    task = Task(
        description=(
            f"Analyze market sentiment for stock ticker {ticker}.\n\n"
            f"Steps to follow:\n"
            f"1. Use AlphaVantageTool to fetch news sentiment scores, "
            f"RSI, and MACD for {ticker}\n"
            f"2. Evaluate news sentiment: how many articles are bullish "
            f"vs bearish? What is the average sentiment score?\n"
            f"3. Interpret RSI: is the stock overbought (>70), "
            f"oversold (<30), or neutral?\n"
            f"4. Interpret MACD: is momentum building or fading?\n"
            f"5. Look for confirmation: do all signals agree, "
            f"or are they conflicting?\n"
            f"6. If RSI/MACD data is unavailable due to API limits, "
            f"focus on news sentiment and note the limitation\n"
            f"7. Produce an overall sentiment verdict"
        ),

        expected_output=(
            "A structured sentiment analysis with these exact sections:\n"
            "SENTIMENT_VERDICT: [BULLISH/BEARISH/NEUTRAL/MIXED]\n"
            "NEWS_SENTIMENT: [Score and summary from professional sources]\n"
            "RSI_SIGNAL: [Value and interpretation, or 'Unavailable']\n"
            "MACD_SIGNAL: [Direction and interpretation, or 'Unavailable']\n"
            "SIGNAL_AGREEMENT: [Do signals confirm each other or conflict?]\n"
            "SUMMARY: [2-3 sentence plain English sentiment summary]"
        ),

        agent=agent,
    )

    return task