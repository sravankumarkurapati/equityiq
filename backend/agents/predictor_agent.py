# backend/agents/predictor_agent.py
#
# The PredictorAgent generates and interprets the price forecast.
#
# It uses ProphetForecasterTool which:
#   - Fetches 2 years of price history via yfinance
#   - Fits a Prophet model (2-5 seconds on CPU)
#   - Returns 7-day daily price predictions with confidence bands
#
# The agent's job is NOT just to run the forecast —
# it interprets what the numbers actually mean:
#   - Is a -2% forecast meaningful or within noise?
#   - Does high confidence (96%) make the signal more actionable?
#   - How does recent momentum align with the forecast direction?
#
# This agent bridges raw ML output and human-readable insight.
# It never just repeats numbers — it explains what they mean
# for someone deciding whether to buy, hold, or sell.
from dotenv import load_dotenv
load_dotenv()

from crewai import Agent, Task, LLM

from backend.ml.prophet_forecaster import ProphetForecasterTool
from backend.config import settings


def create_predictor_agent() -> Agent:
    """
    Creates the PredictorAgent.
    Uses ProphetForecasterTool for 7-day price forecasting.
    """

    llm = LLM(
        model="groq/llama-3.3-70b-versatile",
        # Slightly higher temperature than other agents —
        # interpretation requires more nuanced reasoning
        temperature=0.2,
    )

    prophet_tool = ProphetForecasterTool()

    agent = Agent(
        role="Quantitative Price Forecaster",

        goal=(
            "Generate a 7-day price forecast for a stock using "
            "statistical modeling and interpret what the forecast "
            "means for near-term price action. Provide clear "
            "price targets with confidence context."
        ),

        backstory=(
            "You are a quantitative analyst with a PhD in financial "
            "mathematics and 12 years of experience building price "
            "forecasting models at a systematic hedge fund. "
            "You understand that no forecast is certain — you always "
            "communicate confidence levels and acknowledge uncertainty. "
            "You know Prophet's strengths (trend + seasonality) and "
            "weaknesses (cannot predict sudden news-driven moves). "
            "You contextualize forecasts: a 1% predicted move is noise, "
            "a 5% predicted move with 90%+ confidence is a strong signal. "
            "You always pair the statistical forecast with momentum context."
        ),

        tools=[prophet_tool],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=3,
    )

    return agent


def create_predictor_task(agent: Agent, ticker: str) -> Task:
    """
    Creates the Task for the PredictorAgent.
    Instructs it to run the forecast and provide meaningful interpretation.
    """

    task = Task(
        description=(
            f"Generate and interpret a 7-day price forecast for {ticker}.\n\n"
            f"Steps to follow:\n"
            f"1. Use ProphetForecasterTool to generate the 7-day forecast "
            f"for {ticker}\n"
            f"2. Note the current price and predicted price at day 7\n"
            f"3. Calculate the predicted price change in dollars and percent\n"
            f"4. Assess confidence: is the confidence score above 80%? "
            f"Above 90%? What does that mean?\n"
            f"5. Interpret the daily forecast: is the move gradual or sudden?\n"
            f"6. Note the confidence band width — narrow band means "
            f"higher certainty, wide band means more uncertainty\n"
            f"7. Consider recent momentum — does it align with the forecast?\n"
            f"8. Give a clear PRICE_OUTLOOK: BULLISH / BEARISH / NEUTRAL\n"
            f"9. Important: always remind that this is a statistical model "
            f"and cannot predict sudden news events"
        ),

        expected_output=(
            "A structured price forecast with these exact sections:\n"
            "PRICE_OUTLOOK: [BULLISH/BEARISH/NEUTRAL]\n"
            "CURRENT_PRICE: [Current price in dollars]\n"
            "PREDICTED_PRICE_7D: [Predicted price at day 7]\n"
            "PREDICTED_CHANGE: [Dollar amount and percentage]\n"
            "CONFIDENCE: [Score and what it means]\n"
            "DAILY_TARGETS: [Day-by-day price targets for all 7 days]\n"
            "MOMENTUM: [Recent momentum direction and alignment with forecast]\n"
            "MODEL_NOTE: [One sentence on forecast limitations]\n"
            "SUMMARY: [2-3 sentence plain English forecast summary]"
        ),

        agent=agent,
    )

    return task