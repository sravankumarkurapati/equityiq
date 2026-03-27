# backend/agents/financials_agent.py
#
# The FinancialsAgent analyzes a company's financial health.
#
# It uses two tools:
#   YFinanceTool — price, P/E, EPS, revenue growth, analyst ratings
#   SECTool      — recent 10-Q/10-K filings, insider activity
#
# The agent reads the raw numbers and produces a structured
# assessment: is this company financially healthy or not?
# Is it growing or shrinking? Are insiders buying or selling?
#
# This is the most data-heavy agent — it gets the most raw numbers
# and needs to synthesize them into a clear investment signal.
from dotenv import load_dotenv
load_dotenv()

from crewai import Agent, Task, LLM

from backend.tools.yfinance_tool import YFinanceTool
from backend.tools.sec_tool import SECTool
from backend.config import settings


def create_financials_agent() -> Agent:
    """
    Creates the FinancialsAgent.
    Uses YFinanceTool + SECTool to get comprehensive financial data.
    """

    llm = LLM(
        model="groq/llama-3.3-70b-versatile",
        # Slightly lower temperature for financial analysis
        # We want precise factual reasoning, not creative interpretation
        temperature=0.1,
    )

    yfinance_tool = YFinanceTool()
    sec_tool = SECTool()

    agent = Agent(
        role="Senior Financial Analyst",

        goal=(
            "Analyze a company's financial health, valuation, and growth "
            "trajectory using real financial data. Determine if the stock "
            "is undervalued, fairly valued, or overvalued based on "
            "fundamentals."
        ),

        backstory=(
            "You are a CFA-certified senior financial analyst with 20 years "
            "of experience at Goldman Sachs. You have deep expertise in "
            "reading financial statements, evaluating P/E ratios in context "
            "of growth rates, and identifying balance sheet risks. "
            "You know that a high P/E is acceptable for high-growth companies "
            "but dangerous for slow-growth ones. You always check debt levels "
            "and insider activity as secondary confirmation signals. "
            "You express everything in clear, jargon-free language."
        ),

        # This agent has access to both financial data tools
        tools=[yfinance_tool, sec_tool],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=3,
    )

    return agent


def create_financials_task(agent: Agent, ticker: str) -> Task:
    """
    Creates the Task for the FinancialsAgent.
    Instructs it to use both tools and return a structured assessment.
    """

    task = Task(
        description=(
            f"Perform a comprehensive financial analysis of {ticker}.\n\n"
            f"Steps to follow:\n"
            f"1. Use YFinanceTool to fetch current price, P/E ratio, EPS, "
            f"revenue growth, profit margin, debt/equity, analyst ratings "
            f"and price target for {ticker}\n"
            f"2. Use SECTool to check the most recent 10-Q filing date "
            f"and insider trading activity for {ticker}\n"
            f"3. Evaluate valuation: is the P/E reasonable given growth rate?\n"
            f"4. Assess financial health: debt levels, profit margins\n"
            f"5. Note analyst consensus and upside to price target\n"
            f"6. Check if insiders are buying or selling recently\n"
            f"7. Give an overall financial health rating: STRONG/MODERATE/WEAK"
        ),

        expected_output=(
            "A structured financial analysis with these exact sections:\n"
            "FINANCIAL_HEALTH: [STRONG/MODERATE/WEAK]\n"
            "VALUATION: [UNDERVALUED/FAIR/OVERVALUED] with P/E context\n"
            "KEY_METRICS: [Current price, P/E, EPS, Revenue growth, "
            "Profit margin, Debt/equity]\n"
            "ANALYST_VIEW: [Consensus rating and upside to price target]\n"
            "SEC_SIGNALS: [Latest filing date and insider activity summary]\n"
            "SUMMARY: [2-3 sentence plain English assessment]"
        ),

        agent=agent,
    )

    return task