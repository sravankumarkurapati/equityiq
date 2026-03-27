# backend/agents/critic_agent.py
#
# The CriticAgent is the quality gate of the entire system.
# It runs AFTER all 4 specialist agents have finished.
#
# Its job:
#   Read the outputs from NewsAgent, FinancialsAgent,
#   SentimentAgent, and PredictorAgent and ask:
#     - Do the signals agree with each other?
#     - Are there any contradictions?
#     - Is anything missing or unclear?
#     - What is the overall confidence in this analysis?
#     - What is the final BUY / HOLD / SELL recommendation?
#
# Why a CriticAgent matters:
#   Without validation, agents can produce outputs that look
#   confident but contradict each other. For example:
#     - News is very negative BUT financials are strong
#     - Forecast is bullish BUT sentiment is bearish
#   The CriticAgent catches these conflicts and either
#   explains them or flags them as uncertainty.
#
# This agent has NO tools — it only reads and reasons.
# It operates purely on the text outputs from other agents.
# This is called a "reflection" pattern in agentic AI.
from dotenv import load_dotenv
load_dotenv()

from crewai import Agent, Task, LLM
from backend.config import settings


def create_critic_agent() -> Agent:
    """
    Creates the CriticAgent.
    No tools — this agent only reasons over other agents' outputs.
    """

    llm = LLM(
        model="groq/llama-3.3-70b-versatile",
        # Higher temperature for the critic —
        # it needs to reason carefully and weigh conflicting signals
        # rather than just extracting facts
        temperature=0.3,
    )

    agent = Agent(
        role="Investment Research Quality Analyst",

        goal=(
            "Review and validate the outputs from all specialist agents. "
            "Identify agreements, contradictions, and gaps. "
            "Produce a final validated investment verdict with a "
            "clear BUY / HOLD / SELL recommendation and confidence score."
        ),

        backstory=(
            "You are a managing director at a top investment bank who "
            "has reviewed thousands of research reports. You have a sharp "
            "eye for inconsistencies — you immediately notice when a "
            "bullish forecast contradicts negative news sentiment, or when "
            "strong fundamentals are undermined by insider selling. "
            "You never rubber-stamp reports. If signals conflict you say so "
            "clearly and explain why. Your job is not to be optimistic or "
            "pessimistic — your job is to be accurate. "
            "You always end with a clear actionable recommendation and "
            "you always remind readers that this is not financial advice."
        ),

        # No tools — critic only reads and reasons
        tools=[],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=3,
    )

    return agent


def create_critic_task(
    agent: Agent,
    ticker: str,
    news_output: str,
    financials_output: str,
    sentiment_output: str,
    predictor_output: str,
) -> Task:
    """
    Creates the Task for the CriticAgent.

    Unlike other tasks, this one receives the actual outputs
    from the previous 4 agents as context in the description.
    This is how CrewAI passes information between agents when
    running in sequential mode.

    Args:
        ticker: Stock symbol
        news_output: Raw text output from NewsAgent
        financials_output: Raw text output from FinancialsAgent
        sentiment_output: Raw text output from SentimentAgent
        predictor_output: Raw text output from PredictorAgent
    """

    task = Task(
        description=(
            f"You are reviewing a complete research report for {ticker}.\n\n"
            f"Here are the outputs from each specialist agent:\n\n"
            f"--- NEWS ANALYSIS ---\n{news_output}\n\n"
            f"--- FINANCIAL ANALYSIS ---\n{financials_output}\n\n"
            f"--- SENTIMENT ANALYSIS ---\n{sentiment_output}\n\n"
            f"--- PRICE FORECAST ---\n{predictor_output}\n\n"
            f"Your job:\n"
            f"1. Check if all 4 analyses are complete and coherent\n"
            f"2. Identify where signals AGREE (strengthens conviction)\n"
            f"3. Identify where signals CONFLICT (increases uncertainty)\n"
            f"4. Assess overall data quality — were there any API failures "
            f"or missing data that weakens the analysis?\n"
            f"5. Weigh the evidence and produce a final verdict\n"
            f"6. Assign an overall confidence score 1-100\n"
            f"7. Give a clear BUY / HOLD / SELL recommendation\n"
            f"8. Write a plain English executive summary suitable for "
            f"a retail investor\n"
            f"9. Always include the standard disclaimer at the end"
        ),

        expected_output=(
            "A validated research report with these exact sections:\n"
            "FINAL_VERDICT: [BUY/HOLD/SELL]\n"
            "CONFIDENCE_SCORE: [1-100 with explanation]\n"
            "SIGNAL_ALIGNMENT: [Which signals agree and which conflict]\n"
            "BULL_CASE: [Top 3 reasons to be optimistic]\n"
            "BEAR_CASE: [Top 3 reasons to be cautious]\n"
            "KEY_RISKS: [The most important risks to watch]\n"
            "EXECUTIVE_SUMMARY: [4-5 sentences suitable for a retail "
            "investor — clear, no jargon]\n"
            "DISCLAIMER: This analysis is for informational purposes only "
            "and does not constitute financial advice. Always do your own "
            "research before making investment decisions."
        ),

        agent=agent,
    )

    return task