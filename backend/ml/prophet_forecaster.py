# backend/ml/prophet_forecaster.py
#
# Generates a 7-day stock price forecast using Facebook Prophet.
#
# What Prophet is:
#   A statistical forecasting model built by Meta's data science team.
#   It is NOT a neural network — no GPU needed, no training step.
#   It works by decomposing a time series into components:
#     Trend     — long-term direction (up, down, flat)
#     Seasonality — weekly and yearly patterns
#     Holidays  — market calendar effects
#
# How it works here:
#   1. We fetch 2 years of daily closing prices via yfinance
#   2. We calculate RSI and MACD from those prices (pure math)
#   3. Prophet fits a curve through the data in 2-5 seconds on CPU
#   4. We ask it to predict the next 7 trading days
#   5. It returns: predicted price + upper + lower confidence bounds
#
# The PredictorAgent calls this tool, receives the forecast,
# then uses the LLM to interpret what it means in plain English.

import pandas as pd
import numpy as np
from prophet import Prophet
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
import yfinance as yf
import logging
import warnings

# Suppress Prophet's internal Stan compiler logs
# They are verbose and not useful during normal operation
warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)


class ProphetInput(BaseModel):
    ticker: str = Field(
        description="Stock ticker symbol, e.g. 'TSLA'"
    )
    forecast_days: int = Field(
        default=7,
        description="Number of trading days to forecast ahead"
    )


class ProphetForecasterTool(BaseTool):
    """
    Fits a Facebook Prophet model on 2 years of price history
    and generates a price forecast with confidence intervals.
    Runs entirely on CPU — takes 2-5 seconds per ticker.
    """

    name: str = "ProphetForecasterTool"
    description: str = (
        "Generates a 7-day stock price forecast using Facebook Prophet. "
        "Returns predicted prices with upper/lower confidence bounds, "
        "trend direction, and momentum signals. No GPU required."
    )
    args_schema: type[BaseModel] = ProphetInput

    def _run(self, ticker: str, forecast_days: int = 7) -> dict:
        """
        Full pipeline:
          fetch data → add indicators → fit Prophet → forecast → interpret
        """
        ticker = ticker.upper().strip()
        logger.info(f"ProphetForecaster called for {ticker}, {forecast_days} days")

        try:
            # ── Step 1: Fetch 2 years of price history ────────────
            # We need enough data for Prophet to learn yearly patterns
            # 2 years = ~504 trading days — sufficient for reliable fit
            stock = yf.Ticker(ticker)
            history = stock.history(period="2y")

            if history.empty:
                return {
                    "ticker": ticker,
                    "error": "No price history available",
                    "data_available": False
                }

            if len(history) < 100:
                return {
                    "ticker": ticker,
                    "error": f"Only {len(history)} data points — need at least 100",
                    "data_available": False
                }

            # ── Step 2: Format data for Prophet ───────────────────
            # Prophet requires EXACTLY two columns named 'ds' and 'y':
            #   ds = datestamp (the date)
            #   y  = value to forecast (closing price)
            # Any other column name will cause an error.
            df = history[["Close"]].reset_index()
            df.columns = ["ds", "y"]

            # Remove timezone info — Prophet cannot handle timezone-aware dates
            # yfinance returns timezone-aware dates, so we strip the timezone
            df["ds"] = pd.to_datetime(df["ds"]).dt.tz_localize(None)
            df = df.dropna()

            # ── Step 3: Add technical indicators as extra features ─
            # Prophet can use additional numeric columns as "regressors"
            # These help it understand momentum alongside pure price trends
            df = self._add_technical_indicators(df)

            # ── Step 4: Configure and fit the Prophet model ───────
            model = Prophet(
                # changepoint_prior_scale controls how flexible the trend is
                # 0.15 = moderately flexible (default 0.05 is too rigid for stocks)
                changepoint_prior_scale=0.15,

                # Stock prices have clear weekly patterns
                # (Monday effect, Friday selloffs, etc.)
                weekly_seasonality=True,

                # Yearly patterns: earnings seasons, January effect, etc.
                yearly_seasonality=True,

                # Daily seasonality = False because our data is daily,
                # not intraday (hourly/minute data)
                daily_seasonality=False,

                # Multiplicative seasonality means seasonal swings
                # scale proportionally with the price level.
                # Better for stocks than additive (the default).
                # Example: a 5% seasonal swing on a $100 stock = $5
                #          same 5% on a $1000 stock = $50
                seasonality_mode="multiplicative",

                
            )

            # Add our technical indicator columns as extra regressors
            # Prophet will use these alongside the time patterns
            model.add_regressor("rsi_normalized")
            model.add_regressor("macd_normalized")

            # fit() is where Prophet does its work — 2-5 seconds on Mac
            model.fit(df)

            # ── Step 5: Create future dates to forecast ───────────
            # make_future_dataframe extends the date range by N periods
            # freq="B" means Business days only (skips weekends)
            # This correctly models that stocks don't trade on weekends
            future = model.make_future_dataframe(
                periods=forecast_days,
                freq="B"
            )

            # Fill technical indicator values for future dates
            # We carry forward the last known values
            # (simple but reasonable assumption for short forecasts)
            future = self._fill_future_indicators(future, df)

            # ── Step 6: Generate the forecast ─────────────────────
            # predict() returns a DataFrame with:
            #   yhat       = predicted price (most likely value)
            #   yhat_lower = lower bound of 80% confidence interval
            #   yhat_upper = upper bound of 80% confidence interval
            forecast = model.predict(future)

            # We only want the future rows, not the historical fitted values
            future_forecast = forecast.tail(forecast_days)

            # ── Step 7: Build result ──────────────────────────────
            current_price = float(df["y"].iloc[-1])
            predicted_price_7d = float(future_forecast["yhat"].iloc[-1])

            # How much the price is expected to change over 7 days
            price_change_pct = round(
                ((predicted_price_7d - current_price) / current_price) * 100, 2
            )

            # Classify direction signal
            # > +1.5% = meaningfully bullish
            # < -1.5% = meaningfully bearish
            # in between = effectively flat
            if price_change_pct > 1.5:
                direction = "BULLISH"
            elif price_change_pct < -1.5:
                direction = "BEARISH"
            else:
                direction = "NEUTRAL"

            # Confidence score: narrow prediction band = more confident
            # Wide band = high uncertainty
            avg_band_width = float(
                (future_forecast["yhat_upper"] - future_forecast["yhat_lower"]).mean()
            )
            # Express confidence as percentage (100% = perfectly certain)
            confidence = round(
                max(0, 100 - (avg_band_width / current_price * 100)), 1
            )

            # Build daily breakdown — one row per forecast day
            daily_forecast = []
            for _, row in future_forecast.iterrows():
                daily_forecast.append({
                    "date": row["ds"].strftime("%Y-%m-%d"),
                    "predicted_price": round(float(row["yhat"]), 2),
                    "lower_bound": round(float(row["yhat_lower"]), 2),
                    "upper_bound": round(float(row["yhat_upper"]), 2),
                })

            # Recent momentum: compare last 5 days to previous 5 days
            # Tells us if the stock is accelerating or decelerating
            recent_5d_avg = float(df["y"].tail(5).mean())
            prior_5d_avg = float(df["y"].tail(10).head(5).mean())

            if recent_5d_avg > prior_5d_avg * 1.02:
                momentum = "accelerating upward"
            elif recent_5d_avg < prior_5d_avg * 0.98:
                momentum = "decelerating / falling"
            else:
                momentum = "stable / sideways"

            result = {
                "ticker": ticker,
                "current_price": round(current_price, 2),
                "forecast_horizon_days": forecast_days,
                "predicted_price_7d": round(predicted_price_7d, 2),
                "predicted_change_pct": price_change_pct,
                "direction_signal": direction,
                "confidence_score": confidence,
                "recent_momentum": momentum,
                "daily_forecast": daily_forecast,
                "data_points_used": len(df),
                "model": "Facebook Prophet + RSI/MACD regressors",
                "data_available": True,
            }

            logger.info(
                f"Prophet forecast complete: {ticker} "
                f"direction={direction} change={price_change_pct}%"
            )
            return result

        except Exception as e:
            logger.error(f"ProphetForecaster error for {ticker}: {e}")
            return {
                "ticker": ticker,
                "error": str(e),
                "data_available": False
            }

    def _add_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates RSI and MACD from price data and adds them
        as normalized columns for Prophet to use as regressors.

        Why normalize to [0, 1]:
          Prophet expects all regressors to be on similar scales.
          RSI is 0-100 and MACD can be any value — normalizing both
          prevents one from dominating the model.
        """
        prices = df["y"]

        # ── RSI (14-day) ──────────────────────────────────────────
        # Step 1: Calculate daily price changes
        delta = prices.diff()

        # Step 2: Separate gains and losses
        # Where delta > 0, keep the gain. Where delta <= 0, set to 0.
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)

        # Step 3: Calculate 14-day rolling average of gains and losses
        avg_gain = gain.rolling(window=14).mean()
        avg_loss = loss.rolling(window=14).mean()

        # Step 4: Calculate RS (Relative Strength) and then RSI
        # Replace 0 in avg_loss with NaN to avoid division by zero
        rs = avg_gain / avg_loss.replace(0, float('nan'))
        rsi = 100 - (100 / (1 + rs))

        # Normalize from [0, 100] range to [0, 1] range
        df["rsi_normalized"] = rsi / 100.0

        # ── MACD ──────────────────────────────────────────────────
        # EMA = Exponential Moving Average (weights recent prices more)
        # span=12 = fast EMA, span=26 = slow EMA (standard settings)
        ema_12 = prices.ewm(span=12, adjust=False).mean()
        ema_26 = prices.ewm(span=26, adjust=False).mean()

        # MACD line = fast EMA minus slow EMA
        macd_line = ema_12 - ema_26

        # Normalize by dividing by current price
        # This makes MACD scale-independent across different stock prices
        df["macd_normalized"] = macd_line / prices.replace(0, float('nan'))

        # Fill any NaN values (from rolling window startup period)
        df["rsi_normalized"] = df["rsi_normalized"].fillna(0.5)
        df["macd_normalized"] = df["macd_normalized"].fillna(0.0)

        return df

    def _fill_future_indicators(
        self,
        future: pd.DataFrame,
        historical: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Fills indicator values for future dates.
        We carry forward the last known values — this is a standard
        approach for short-term forecasts where we have no future data.
        """
        last_rsi = float(historical["rsi_normalized"].iloc[-1])
        last_macd = float(historical["macd_normalized"].iloc[-1])

        # Merge historical indicator values for past dates
        future = future.merge(
            historical[["ds", "rsi_normalized", "macd_normalized"]],
            on="ds",
            how="left"
        )

        # For future dates (NaN after merge), use last known values
        future["rsi_normalized"] = future["rsi_normalized"].fillna(last_rsi)
        future["macd_normalized"] = future["macd_normalized"].fillna(last_macd)

        return future