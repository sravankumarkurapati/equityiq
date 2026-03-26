# backend/config.py
#
# Single source of truth for ALL configuration in the project.
# Every other file imports settings from here.
#
# How it works:
#   1. You put real values in .env (never committed to Git)
#   2. Pydantic reads .env automatically when the app starts
#   3. Any file can access settings by importing:
#      from backend.config import settings
#      then use: settings.groq_api_key

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """
    Each variable here maps directly to a key in your .env file.
    Pydantic validates the type — if you put text where an int
    is expected it raises a clear error immediately at startup.
    """

    # ── LLM ──────────────────────────────────────────────────────
    # Groq runs Llama 3.3 70B on their servers for free.
    # Your Mac never does LLM inference — just sends API calls.
    groq_api_key: str

    # ── News ──────────────────────────────────────────────────────
    # NewsAPI free tier = 100 requests/day
    # Used by the NewsAgent to fetch recent headlines
    news_api_key: str

    # ── Alpha Vantage ─────────────────────────────────────────────
    # Free tier = 25 requests/day
    # Used by SentimentAgent for professional news sentiment scores
    # Also provides RSI, MACD backup if yfinance fails
    alpha_vantage_key: str

    # ── AWS ───────────────────────────────────────────────────────
    # On your Mac: these are read from .env
    # On EC2 later: the server's IAM role handles auth automatically
    # so you won't need these hardcoded values in production
    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # ── AWS resource names ────────────────────────────────────────
    # Must match the exact names you created in AWS Console
    dynamo_table_analyses: str = "equityiq_analyses"
    dynamo_table_daily_picks: str = "equityiq_daily_picks"
    s3_bucket_name: str = "equityiq-reports"

    # ── Cache ─────────────────────────────────────────────────────
    # If someone searches AAPL and another person searches AAPL
    # within 30 minutes, the second person gets the cached result.
    # Saves API calls + makes the app feel instant.
    cache_ttl_seconds: int = 1800  # 1800 seconds = 30 minutes

    # ── Internal URL ─────────────────────────────────────────────
    # Inside Docker, containers talk to each other by service name.
    # 'fastapi' is the service name in docker-compose.yml.
    # Outside Docker (direct Python run), use http://localhost:8000
    api_base_url: str = "http://fastapi:8000"

    # ── Environment ───────────────────────────────────────────────
    # Controls logging verbosity and feature flags
    # "development" on Mac, "production" on EC2
    app_env: str = "development"

    @property
    def is_production(self) -> bool:
        """
        Shortcut check used across the codebase.
        Example:
            if settings.is_production:
                send_cloudwatch_logs()
        """
        return self.app_env == "production"

    class Config:
        # Look for a .env file and load it
        env_file = ".env"
        # If .env has keys not defined above, ignore them silently
        extra = "ignore"
        # GROQ_API_KEY in .env matches groq_api_key here
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """
    @lru_cache ensures this runs exactly ONCE per app lifetime.
    Every import of 'settings' across all files gets the same object.
    No repeated file reads, no inconsistent values.
    """
    return Settings()


# This is the object every other file imports:
#   from backend.config import settings
settings = get_settings()