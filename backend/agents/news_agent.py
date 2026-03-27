# backend/agents/news_agent.py
#
# The NewsAgent is responsible for one job:
#   Fetch recent news about a stock and produce a structured
#   summary of what's happening in plain English.
#
# How CrewAI agents work:
#   Each agent has:
#     role        — who the agent is (like a job title)
#     goal        — what it's trying to achieve
#     backstory   — context that shapes how the LLM reasons
#     tools       — the data tools it can call
#     llm         — the language model that powers it
#
#   The agent receives a Task which describes exactly what
#   to do and what format to return results in.
#
# This agent uses:
#   NewsTool     — fetches headlines and article summaries
#   The LLM then reads those articles and produces a structured
#   sentiment summary with key themes and risk flags.
from dotenv import load_dotenv
load_dotenv()

from crewai import Agent, Task
from crewai import LLM

from backend.tools.news_tool import NewsTool
from backend.config import settings


def create_news_agent() -> Agent:
    """
    Creates and returns the NewsAgent.

    We use a factory function (create_X) rather than a global object
    so each crew run gets a fresh agent instance.
    This prevents state from leaking between different ticker analyses.
    """

    # Newer CrewAI versions accept a string in format "provider/model"
    # and read the API key from environment variables automatically.
    # GROQ_API_KEY in your .env is picked up automatically by CrewAI.
    llm = LLM(
        model="groq/llama-3.3-70b-versatile",
        temperature=0.1,
    )

    # ── Tool instances ────────────────────────────────────────────
    # Each agent gets its own tool instance
    news_tool = NewsTool()

    # ── Agent definition ──────────────────────────────────────────
    agent = Agent(
        role="Financial News Analyst",

        goal=(
            "Fetch and analyze recent news about a stock to identify "
            "key themes, sentiment, and risk events that could impact "
            "the stock price in the next 7 days."
        ),

        backstory=(
            "You are a senior financial news analyst with 15 years of "
            "experience at Bloomberg. You have a talent for quickly "
            "identifying which news stories actually move stock prices "
            "versus noise. You always distinguish between company-specific "
            "news and broader market/sector news. You flag regulatory risks, "
            "earnings surprises, product launches, and leadership changes "
            "as high-priority signals."
        ),

        tools=[news_tool],
        llm=llm,

        # verbose=True prints the agent's reasoning steps to terminal
        # Very useful during development to see what the agent is doing
        verbose=True,

        # allow_delegation=False means this agent cannot hand off work
        # to other agents. Each agent stays in its lane.
        allow_delegation=False,

        # Max iterations before the agent gives up on a task
        # Prevents infinite loops if the LLM gets confused
        max_iter=3,
    )

    return agent


def create_news_task(agent: Agent, ticker: str, company_name: str = "") -> Task:
    """
    Creates the Task that tells the NewsAgent exactly what to do.

    A Task has:
      description  — detailed instructions for the agent
      expected_output — exact format the agent must return
      agent        — which agent runs this task
    """

    task = Task(
        description=(
            f"Analyze recent news for stock ticker {ticker} "
            f"{'('+company_name+')' if company_name else ''}.\n\n"
            f"Steps to follow:\n"
            f"1. Use the NewsTool to fetch articles for {ticker} "
            f"from the past 7 days\n"
            f"2. Read each article carefully\n"
            f"3. Identify the 3 most impactful stories\n"
            f"4. Determine overall news sentiment: Positive, Negative, or Neutral\n"
            f"5. Flag any major risk events (lawsuits, recalls, investigations, "
            f"earnings misses, CEO departures)\n"
            f"6. Note any positive catalysts (product launches, partnerships, "
            f"earnings beats, analyst upgrades)"
        ),

        expected_output=(
            "A structured news analysis with these exact sections:\n"
            "NEWS_SENTIMENT: [Positive/Negative/Neutral]\n"
            "KEY_STORIES: [3 bullet points with date and source]\n"
            "RISK_FLAGS: [Any major risks, or 'None identified']\n"
            "POSITIVE_CATALYSTS: [Any positive news, or 'None identified']\n"
            "SUMMARY: [2-3 sentence plain English summary]"
        ),

        agent=agent,
    )

    return task