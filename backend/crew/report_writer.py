# backend/crew/report_writer.py
#
# The ReportWriter takes the CriticAgent's validated output
# and formats it into a clean structured dict that:
#   - The FastAPI backend returns as JSON
#   - The Streamlit frontend renders as a visual report
#   - DynamoDB stores for caching
#
# Why a separate report writer:
#   The CriticAgent produces free-form text with labeled sections.
#   The ReportWriter parses that text into a proper Python dict
#   with consistent keys that the rest of the system depends on.
#   This separation means the API and UI never deal with raw
#   agent text — they always get clean structured data.
#
# This is NOT a CrewAI agent — it is a plain Python class.
# It runs after the crew finishes, not as part of the crew.

import re
from datetime import datetime, timezone


class ReportWriter:
    """
    Parses raw CriticAgent output text into a structured report dict.
    Also assembles all agent outputs into one unified document.
    """

    def build_report(
        self,
        ticker: str,
        news_output: str,
        financials_output: str,
        sentiment_output: str,
        predictor_output: str,
        critic_output: str,
        forecast_data: dict,
    ) -> dict:
        """
        Assembles the complete final report.

        Args:
            ticker: Stock symbol e.g. "AAPL"
            news_output: Raw text from NewsAgent
            financials_output: Raw text from FinancialsAgent
            sentiment_output: Raw text from SentimentAgent
            predictor_output: Raw text from PredictorAgent
            critic_output: Raw text from CriticAgent
            forecast_data: Structured dict from ProphetForecasterTool
                           (used for the chart data in Streamlit)

        Returns:
            A structured dict with all report sections + metadata
        """

        # Parse the critic output into structured fields
        parsed = self._parse_critic_output(critic_output)

        # Build the complete report
        report = {
            # ── Identity ──────────────────────────────────────────
            "ticker": ticker.upper(),
            "generated_at": datetime.now(timezone.utc).isoformat(),

            # ── Final verdict from CriticAgent ────────────────────
            # These are the most important fields — shown prominently in UI
            "final_verdict": parsed.get("FINAL_VERDICT", "HOLD"),
            "confidence_score": parsed.get("CONFIDENCE_SCORE", "N/A"),
            "signal_alignment": parsed.get("SIGNAL_ALIGNMENT", ""),
            "bull_case": parsed.get("BULL_CASE", ""),
            "bear_case": parsed.get("BEAR_CASE", ""),
            "key_risks": parsed.get("KEY_RISKS", ""),
            "executive_summary": parsed.get("EXECUTIVE_SUMMARY", ""),
            "disclaimer": parsed.get(
                "DISCLAIMER",
                "This analysis is for informational purposes only and "
                "does not constitute financial advice."
            ),

            # ── Raw agent outputs ─────────────────────────────────
            # Stored so the UI can show detailed sections if user wants
            "sections": {
                "news": news_output,
                "financials": financials_output,
                "sentiment": sentiment_output,
                "forecast": predictor_output,
                "validation": critic_output,
            },

            # ── Chart data ────────────────────────────────────────
            # Structured forecast from Prophet — used by Streamlit
            # to draw the price forecast chart with confidence bands
            "forecast_chart_data": {
                "current_price": forecast_data.get("current_price"),
                "predicted_price_7d": forecast_data.get("predicted_price_7d"),
                "predicted_change_pct": forecast_data.get("predicted_change_pct"),
                "direction_signal": forecast_data.get("direction_signal"),
                "confidence_score": forecast_data.get("confidence_score"),
                "daily_forecast": forecast_data.get("daily_forecast", []),
                "momentum": forecast_data.get("recent_momentum"),
            },

            # ── Status ────────────────────────────────────────────
            "status": "complete",
        }

        return report

    def _parse_critic_output(self, text: str) -> dict:
        """
        Parses the CriticAgent's free-form text output into a dict.

        The CriticAgent returns text like:
            FINAL_VERDICT: BUY
            CONFIDENCE_SCORE: 78 - signals mostly align
            BULL_CASE: Strong revenue growth...
            ...

        We extract each labeled section using regex.
        The pattern looks for a LABEL: followed by content
        up until the next LABEL: or end of text.
        """
        parsed = {}

        # These are the section labels we expect in the critic output
        # Order matters — we use them to find where each section ends
        section_labels = [
            "FINAL_VERDICT",
            "CONFIDENCE_SCORE",
            "SIGNAL_ALIGNMENT",
            "BULL_CASE",
            "BEAR_CASE",
            "KEY_RISKS",
            "EXECUTIVE_SUMMARY",
            "DISCLAIMER",
        ]

        for label in section_labels:
            # Regex pattern explanation:
            #   {label}:    — match the label followed by colon
            #   \s*         — optional whitespace after colon
            #   (.*?)       — capture everything (non-greedy)
            #   (?=         — stop when we see...
            #     [A-Z_]+:  — another label (all caps + underscore + colon)
            #     |$        — or end of string
            #   )
            pattern = rf"{label}:\s*(.*?)(?=[A-Z_]{{3,}}:|$)"
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)

            if match:
                # Clean up the extracted text:
                # strip() removes leading/trailing whitespace
                value = match.group(1).strip()
                # Remove any trailing newlines and extra spaces
                value = re.sub(r'\n+', ' ', value).strip()
                parsed[label] = value

        # Normalize the verdict to uppercase BUY/HOLD/SELL
        # In case the LLM returns "buy" or "Buy" instead of "BUY"
        if "FINAL_VERDICT" in parsed:
            verdict = parsed["FINAL_VERDICT"].upper()
            if "BUY" in verdict and "SELL" not in verdict:
                parsed["FINAL_VERDICT"] = "BUY"
            elif "SELL" in verdict:
                parsed["FINAL_VERDICT"] = "SELL"
            else:
                parsed["FINAL_VERDICT"] = "HOLD"

        return parsed

    def format_for_display(self, report: dict) -> str:
        """
        Creates a plain text version of the report.
        Used for terminal output during development and testing.
        The Streamlit UI uses the structured dict directly.
        """
        ticker = report.get("ticker", "UNKNOWN")
        verdict = report.get("final_verdict", "N/A")
        confidence = report.get("confidence_score", "N/A")
        summary = report.get("executive_summary", "N/A")
        forecast = report.get("forecast_chart_data", {})

        lines = [
            "=" * 60,
            f"EQUITYIQ RESEARCH REPORT — {ticker}",
            f"Generated: {report.get('generated_at', 'N/A')}",
            "=" * 60,
            "",
            f"VERDICT    : {verdict}",
            f"CONFIDENCE : {confidence}",
            "",
            f"PRICE NOW  : ${forecast.get('current_price', 'N/A')}",
            f"7D TARGET  : ${forecast.get('predicted_price_7d', 'N/A')}",
            f"CHANGE     : {forecast.get('predicted_change_pct', 'N/A')}%",
            f"DIRECTION  : {forecast.get('direction_signal', 'N/A')}",
            "",
            "EXECUTIVE SUMMARY",
            "-" * 40,
            summary,
            "",
            "BULL CASE",
            "-" * 40,
            report.get("bull_case", "N/A"),
            "",
            "BEAR CASE",
            "-" * 40,
            report.get("bear_case", "N/A"),
            "",
            "KEY RISKS",
            "-" * 40,
            report.get("key_risks", "N/A"),
            "",
            "DISCLAIMER",
            "-" * 40,
            report.get("disclaimer", "N/A"),
            "=" * 60,
        ]

        return "\n".join(lines)