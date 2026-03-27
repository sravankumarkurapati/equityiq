# backend/api/main.py
#
# This is the FastAPI application entry point.
# FastAPI is a modern Python web framework that:
#   - Automatically generates API documentation at /docs
#   - Validates request/response data using Pydantic
#   - Supports async operations natively
#   - Is production-grade (used by Uber, Netflix, Microsoft)
#
# How the API fits into the system:
#   Browser/Streamlit → FastAPI → CrewAI crew → DynamoDB → response
#
# Endpoints we expose:
#   GET  /health              — Docker healthcheck
#   POST /analyze/{ticker}    — trigger full crew analysis
#   GET  /report/{ticker}     — get latest cached report
#   GET  /top5                — get today's top 5 picks
#   GET  /history             — get last 20 analyses
#   GET  /docs                — auto-generated API documentation

import os
from dotenv import load_dotenv

# Load .env FIRST before any other imports
# FastAPI starts as a module so we must ensure env vars are loaded
load_dotenv()
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY", "")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from backend.api.routes.analyze import router as analyze_router
from backend.api.routes.reports import router as reports_router

# Configure logging — outputs to stdout which Docker captures
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ── Create FastAPI app ────────────────────────────────────────────
app = FastAPI(
    title="EquityIQ API",
    description=(
        "Real-time AI stock research platform powered by CrewAI. "
        "Analyzes stocks using 5 specialized agents and Prophet forecasting."
    ),
    version="1.0.0",
    # Docs available at /docs (Swagger UI)
    # Alternative docs at /redoc
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS Middleware ───────────────────────────────────────────────
# CORS = Cross-Origin Resource Sharing
# Without this, the Streamlit frontend (port 8501) cannot call
# the FastAPI backend (port 8000) — browsers block cross-origin requests
# In production, replace "*" with your actual domain
app.add_middleware(
    CORSMiddleware,
    # Allow requests from any origin during development
    # In production: ["https://yourdomain.com"]
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],    # GET, POST, PUT, DELETE etc
    allow_headers=["*"],
)

# ── Register routers ──────────────────────────────────────────────
# Routers are groups of related endpoints defined in separate files
# prefix="/api" means all routes start with /api
# e.g. /analyze/{ticker} becomes /api/analyze/{ticker}
app.include_router(analyze_router, prefix="/api", tags=["Analysis"])
app.include_router(reports_router, prefix="/api", tags=["Reports"])


# ── Root endpoint ─────────────────────────────────────────────────
@app.get("/")
async def root():
    """
    Root endpoint — confirms API is running.
    Also shown when you visit http://localhost:8000 in browser.
    """
    return {
        "name": "EquityIQ API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


# ── Health check endpoint ─────────────────────────────────────────
@app.get("/health")
async def health_check():
    """
    Docker uses this endpoint to check if the container is healthy.
    If this returns 200, Docker considers the container running.
    If this fails, Docker restarts the container automatically.
    """
    return {"status": "healthy"}


# ── Startup event ─────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    """
    Runs once when FastAPI starts.
    Good place to initialize connections and log startup info.
    """
    logger.info("EquityIQ API starting up...")
    logger.info(f"Groq API key loaded: {'yes' if os.getenv('GROQ_API_KEY') else 'NO - CHECK .env'}")
    logger.info("API docs available at http://localhost:8000/docs")


@app.on_event("shutdown")
async def shutdown_event():
    """Runs when FastAPI shuts down — cleanup goes here."""
    logger.info("EquityIQ API shutting down...")