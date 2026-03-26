# backend/tools/sec_tool.py
#
# Fetches SEC (Securities and Exchange Commission) filing data.
# SEC data is 100% free and public — no API key needed.
#
# What the SEC is:
#   The US government agency that requires all public companies
#   to file financial reports. Every public company must file:
#     10-Q — quarterly financial report (4x per year)
#     10-K — annual financial report (1x per year)
#     8-K  — major event disclosure (earnings, CEO change, etc.)
#     Form 4 — when insiders (executives) buy or sell stock
#
# Why this matters for our agents:
#   - Recent 10-Q tells us if revenue/profit is growing or shrinking
#   - Form 4 insider buying is one of the strongest bullish signals
#   - 8-K filings reveal major company events before they hit news
#
# EDGAR is SEC's public database: https://www.sec.gov/edgar

import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
import logging
import time

logger = logging.getLogger(__name__)

# SEC requires this header on every request.
# They use it to identify who is making the request.
# Format: "AppName/Version contact@email.com"
SEC_HEADERS = {
    "User-Agent": "EquityIQ/1.0 equityiq@research.com",
    "Accept-Encoding": "gzip, deflate",
}


class SECInput(BaseModel):
    ticker: str = Field(
        description="Stock ticker symbol, e.g. 'AAPL'"
    )


class SECTool(BaseTool):
    """
    Fetches SEC EDGAR filings for a company.
    Returns recent 10-Q/10-K filings and insider transaction activity.
    """

    name: str = "SECTool"
    description: str = (
        "Fetches SEC EDGAR data for a company including recent 10-Q "
        "and 10-K filings, and insider buying/selling activity from "
        "Form 4 filings. No API key required."
    )
    args_schema: type[BaseModel] = SECInput

    def _run(self, ticker: str) -> dict:
        """
        Main execution method called by the FinancialsAgent.
        Runs 3 steps: find CIK → get filings → get insider trades.
        """
        ticker = ticker.upper().strip()
        logger.info(f"SECTool called for {ticker}")

        try:
            # Step 1: Get the company's CIK number
            # CIK = Central Index Key, SEC's internal ID for each company
            # We need this to look up their specific filings
            cik = self._get_cik(ticker)

            if not cik:
                return {
                    "ticker": ticker,
                    "error": f"Could not find SEC CIK for ticker {ticker}",
                    "data_available": False
                }

            # Step 2: Get list of recent filings for this company
            filings = self._get_recent_filings(cik)

            # Step 3: Get insider trading activity
            # This is a separate search on Form 4 filings
            insider_summary = self._get_insider_activity(ticker)

            result = {
                "ticker": ticker,
                "cik": cik,
                "recent_filings": filings,
                "insider_activity": insider_summary,
                "data_available": True,
            }

            logger.info(f"SECTool success for {ticker}: {len(filings)} filings found")
            return result

        except Exception as e:
            logger.error(f"SECTool error for {ticker}: {e}")
            return {
                "ticker": ticker,
                "error": str(e),
                "data_available": False
            }

    def _get_cik(self, ticker: str) -> str | None:
        """
        Looks up a company's CIK from their ticker symbol.

        SEC provides a public JSON file that maps every ticker
        to its CIK number. We download this file and search it.

        The CIK must be zero-padded to 10 digits for EDGAR URLs.
        Example: Apple's CIK is 320193, padded to 0000320193
        """
        url = "https://www.sec.gov/files/company_tickers.json"

        # Small delay to be respectful to SEC servers
        # SEC rate limit is 10 requests/second
        time.sleep(0.1)

        resp = requests.get(url, headers=SEC_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # The JSON structure is:
        # {
        #   "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        #   "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
        #   ...
        # }
        for entry in data.values():
            if entry.get("ticker", "").upper() == ticker:
                # Zero-pad to 10 digits — required format for EDGAR API
                return str(entry["cik_str"]).zfill(10)

        return None

    def _get_recent_filings(self, cik: str) -> list[dict]:
        """
        Fetches the company's most recent SEC filings.

        The EDGAR submissions API returns a JSON with all filings
        for a company. We filter to the important types:
          10-Q = quarterly report (most important for recent financials)
          10-K = annual report
          8-K  = material event (earnings surprise, CEO change, etc.)
        """
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"

        time.sleep(0.1)
        resp = requests.get(url, headers=SEC_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # The filings data has parallel arrays — each index corresponds
        # to the same filing across all arrays
        # e.g. form[0], date[0], document[0] all describe filing #0
        filings_data = data.get("filings", {}).get("recent", {})
        if not filings_data:
            return []

        forms = filings_data.get("form", [])
        dates = filings_data.get("filingDate", [])
        descriptions = filings_data.get("primaryDocument", [])
        accession_numbers = filings_data.get("accessionNumber", [])

        # Only care about these filing types
        important_forms = {"10-Q", "10-K", "8-K"}
        filings = []

        for form, date, doc, accession in zip(forms, dates, descriptions, accession_numbers):
            if form in important_forms:
                # Build the direct URL to view this filing on SEC website
                # Useful for including in the report for reference
                accession_clean = accession.replace("-", "")
                filing_url = (
                    f"https://www.sec.gov/Archives/edgar/data/"
                    f"{int(accession_clean[:10])}/{accession_clean}/{doc}"
                )

                filings.append({
                    "form_type": form,
                    "filing_date": date,
                    "document": doc,
                    "url": filing_url,
                })

            # Stop after 6 filings — enough context for the agent
            if len(filings) >= 6:
                break

        return filings

    def _get_insider_activity(self, ticker: str) -> dict:
        """
        Searches for recent Form 4 filings for this ticker.

        Form 4 is filed within 2 business days whenever a company
        executive, director, or 10%+ shareholder buys or sells stock.

        Why it matters:
          - Insiders buying their own stock = strong confidence signal
          - Insiders selling = could mean they think stock is overvalued
            (but also could just be diversification — less clear signal)

        We use EDGAR's full-text search to count recent Form 4 filings.
        """
        url = (
            f"https://efts.sec.gov/LATEST/search-index?"
            f"q=%22{ticker}%22&forms=4"
        )

        try:
            time.sleep(0.1)
            resp = requests.get(url, headers=SEC_HEADERS, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            # Total number of Form 4 filings mentioning this ticker
            total = data.get("hits", {}).get("total", {}).get("value", 0)

            return {
                "total_insider_filings": total,
                "interpretation": (
                    "High insider filing count suggests active insider trading. "
                    "Check recent filings to determine if buying or selling."
                )
            }

        except Exception as e:
            # Insider data is supplementary — don't fail entire tool
            logger.warning(f"Could not fetch insider data for {ticker}: {e}")
            return {
                "total_insider_filings": None,
                "error": "Could not fetch insider activity"
            }