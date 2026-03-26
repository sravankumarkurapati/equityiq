# backend/db/dynamo_client.py
#
# All database operations for the project in one place.
# We use AWS DynamoDB — a NoSQL key-value database.
#
# Why DynamoDB:
#   - Free forever (25GB on AWS free tier)
#   - No server to manage — fully serverless
#   - Works perfectly for storing JSON analysis reports
#   - Fast single-item lookups by ticker + date
#
# Two tables we interact with:
#
#   equityiq_analyses
#     Stores every full analysis report ever run.
#     Partition key: ticker (e.g. "AAPL")
#     Sort key: timestamp (e.g. "2026-03-26T13:44:43")
#     We query by ticker to get the latest analysis.
#
#   equityiq_daily_picks
#     Stores the Top 5 picks generated each morning by Lambda.
#     Partition key: date (e.g. "2026-03-26")
#     We query by today's date to show the landing page.
#
# boto3 is the official AWS Python SDK.
# It automatically uses credentials from:
#   1. Environment variables (AWS_ACCESS_KEY_ID etc.) — used locally
#   2. EC2 instance IAM role — used in production automatically

import boto3
import json
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key
import logging

from backend.config import settings

logger = logging.getLogger(__name__)


def _get_dynamodb():
    """
    Creates and returns a DynamoDB resource.

    boto3 automatically picks up credentials from environment variables.
    On EC2, it uses the instance IAM role instead — no credentials needed.

    We use 'resource' (high-level API) rather than 'client' (low-level)
    because it handles type conversions automatically.
    For example, Python dicts become DynamoDB Maps without manual conversion.
    """
    return boto3.resource(
        "dynamodb",
        region_name=settings.aws_region,
        # These are empty strings in production (EC2 uses IAM role)
        # In local dev they are read from .env
        aws_access_key_id=settings.aws_access_key_id or None,
        aws_secret_access_key=settings.aws_secret_access_key or None,
    )


def save_analysis(ticker: str, analysis_data: dict) -> bool:
    """
    Saves a complete analysis report to DynamoDB.

    Called after the CrewAI crew finishes running for a ticker.
    The full JSON report is stored so we can retrieve it later
    without re-running the agents.

    Args:
        ticker: Stock symbol e.g. "AAPL"
        analysis_data: Full report dict from the crew

    Returns:
        True if saved successfully, False if error
    """
    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(settings.dynamo_table_analyses)

        # Generate timestamp for this analysis
        # ISO format: "2026-03-26T13:44:43+00:00"
        timestamp = datetime.now(timezone.utc).isoformat()

        # DynamoDB item — partition key + sort key + data
        item = {
            "ticker": ticker.upper(),          # partition key
            "timestamp": timestamp,             # sort key
            # TTL: Unix timestamp 7 days from now
            # DynamoDB automatically deletes items after this time
            # This prevents old stale analyses from accumulating forever
            "ttl": int(datetime.now(timezone.utc).timestamp()) + (7 * 24 * 3600),
            # Store the full analysis as a JSON string
            # DynamoDB has limits on nested object depth so JSON string is safer
            "report_json": json.dumps(analysis_data),
            # Store key fields at top level for easy querying
            "direction": analysis_data.get("direction_signal", "UNKNOWN"),
            "confidence": str(analysis_data.get("confidence_score", 0)),
        }

        table.put_item(Item=item)
        logger.info(f"Saved analysis for {ticker} at {timestamp}")
        return True

    except Exception as e:
        logger.error(f"Failed to save analysis for {ticker}: {e}")
        return False


def get_latest_analysis(ticker: str) -> dict | None:
    """
    Retrieves the most recent analysis for a ticker.

    Uses a DynamoDB Query with ScanIndexForward=False to get
    the most recent item first (sort key is timestamp, descending).

    Returns None if no analysis exists yet for this ticker.
    """
    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(settings.dynamo_table_analyses)

        # Query all items with this ticker (partition key)
        # ScanIndexForward=False = newest first (descending sort key order)
        # Limit=1 = only get the single most recent item
        response = table.query(
            KeyConditionExpression=Key("ticker").eq(ticker.upper()),
            ScanIndexForward=False,
            Limit=1,
        )

        items = response.get("Items", [])
        if not items:
            logger.info(f"No existing analysis found for {ticker}")
            return None

        # Parse the JSON string back into a Python dict
        item = items[0]
        report = json.loads(item["report_json"])

        # Attach the timestamp so the caller knows how fresh this is
        report["_saved_at"] = item["timestamp"]

        logger.info(f"Retrieved analysis for {ticker} from {item['timestamp']}")
        return report

    except Exception as e:
        logger.error(f"Failed to retrieve analysis for {ticker}: {e}")
        return None


def is_analysis_fresh(ticker: str) -> bool:
    """
    Checks if the latest analysis for a ticker is still fresh
    (within the cache TTL window).

    Used by the API to decide whether to:
      - Return the cached DynamoDB result immediately (fresh)
      - Re-run the CrewAI agents (stale or missing)

    Returns True if analysis exists and is within TTL window.
    """
    try:
        analysis = get_latest_analysis(ticker)
        if not analysis:
            return False

        saved_at_str = analysis.get("_saved_at")
        if not saved_at_str:
            return False

        # Parse the saved timestamp
        saved_at = datetime.fromisoformat(saved_at_str)
        now = datetime.now(timezone.utc)

        # Calculate age in seconds
        age_seconds = (now - saved_at).total_seconds()

        # Compare to our cache TTL setting (default 1800 = 30 minutes)
        is_fresh = age_seconds < settings.cache_ttl_seconds

        logger.info(
            f"Cache check for {ticker}: "
            f"age={int(age_seconds)}s, "
            f"ttl={settings.cache_ttl_seconds}s, "
            f"fresh={is_fresh}"
        )
        return is_fresh

    except Exception as e:
        logger.error(f"Cache freshness check failed for {ticker}: {e}")
        # If we can't check, assume stale — safer to re-run than serve wrong data
        return False


def save_daily_picks(date: str, picks: list[dict]) -> bool:
    """
    Saves the Top 5 daily stock picks generated by the Lambda screener.

    Called every morning at 8:30 AM ET by the EventBridge Lambda.
    The Streamlit home page reads from this table to show
    the daily picks without running agents on every page load.

    Args:
        date: Date string e.g. "2026-03-26"
        picks: List of 5 dicts, each with ticker + rationale + signal
    """
    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(settings.dynamo_table_daily_picks)

        item = {
            "date": date,                          # partition key
            "picks_json": json.dumps(picks),       # the 5 picks as JSON
            "generated_at": datetime.now(timezone.utc).isoformat(),
            # Keep for 48 hours then auto-delete (stale picks not useful)
            "ttl": int(datetime.now(timezone.utc).timestamp()) + (48 * 3600),
        }

        table.put_item(Item=item)
        logger.info(f"Saved {len(picks)} daily picks for {date}")
        return True

    except Exception as e:
        logger.error(f"Failed to save daily picks for {date}: {e}")
        return False


def get_daily_picks(date: str) -> list[dict] | None:
    """
    Retrieves the Top 5 picks for a specific date.

    Called by the Streamlit home page on load.
    Returns None if no picks have been generated yet for today
    (e.g. before 8:30 AM ET or if Lambda hasn't run yet).
    """
    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(settings.dynamo_table_daily_picks)

        # get_item does a direct key lookup — very fast, no scanning
        response = table.get_item(Key={"date": date})
        item = response.get("Item")

        if not item:
            logger.info(f"No daily picks found for {date}")
            return None

        picks = json.loads(item["picks_json"])
        logger.info(f"Retrieved {len(picks)} daily picks for {date}")
        return picks

    except Exception as e:
        logger.error(f"Failed to retrieve daily picks for {date}: {e}")
        return None


def list_recent_analyses(limit: int = 20) -> list[dict]:
    """
    Returns the most recent analyses across all tickers.
    Used by the History page in Streamlit.

    Note: DynamoDB Scan reads the entire table — fine for small tables
    but would need a GSI (Global Secondary Index) for large scale.
    For our portfolio project, scan is perfectly adequate.
    """
    try:
        dynamodb = _get_dynamodb()
        table = dynamodb.Table(settings.dynamo_table_analyses)

        # Scan gets all items — we then sort by timestamp in Python
        response = table.scan(
            # Only fetch summary fields — not the full report JSON
            # This keeps the response small and fast
            ProjectionExpression="ticker, #ts, direction, confidence",
            # 'timestamp' is a reserved word in DynamoDB so we alias it
            ExpressionAttributeNames={"#ts": "timestamp"},
        )

        items = response.get("Items", [])

        # Sort by timestamp descending (most recent first)
        items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        # Return only the requested number of items
        return items[:limit]

    except Exception as e:
        logger.error(f"Failed to list recent analyses: {e}")
        return []