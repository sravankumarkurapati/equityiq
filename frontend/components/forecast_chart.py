# frontend/components/forecast_chart.py
#
# Renders the Prophet 7-day price forecast chart using Plotly.
# Shows predicted price line + confidence band (upper/lower bounds).

import streamlit as st
import plotly.graph_objects as go


def render_forecast_chart(
    ticker: str,
    daily_forecast: list,
    current_price: float,
    predicted_price: float,
):
    """
    Renders an interactive Plotly chart showing:
      - Predicted price line (blue)
      - Confidence band (shaded area between upper/lower bounds)
      - Current price reference line (dashed white)
      - Predicted 7-day target reference line (dashed green/red)

    Args:
        ticker: Stock symbol for chart title
        daily_forecast: List of {date, predicted_price,
                         lower_bound, upper_bound}
        current_price: Today's price (reference line)
        predicted_price: Day 7 predicted price
    """

    if not daily_forecast:
        return

    dates = [d["date"] for d in daily_forecast]
    predicted = [d["predicted_price"] for d in daily_forecast]
    lower = [d["lower_bound"] for d in daily_forecast]
    upper = [d["upper_bound"] for d in daily_forecast]

    # Direction color
    is_bullish = (predicted_price or 0) > (current_price or 0)
    line_color = "#10b981" if is_bullish else "#ef4444"
    fill_color = (
        "rgba(16,185,129,0.12)" if is_bullish
        else "rgba(239,68,68,0.12)"
    )

    fig = go.Figure()

    # ── Confidence band ───────────────────────────────────────────
    # Upper bound line (invisible — just for fill reference)
    fig.add_trace(go.Scatter(
        x=dates,
        y=upper,
        mode="lines",
        line=dict(width=0),
        showlegend=False,
        hoverinfo="skip",
    ))

    # Lower bound with fill to upper
    fig.add_trace(go.Scatter(
        x=dates,
        y=lower,
        mode="lines",
        line=dict(width=0),
        fill="tonexty",
        fillcolor=fill_color,
        name="Confidence Band",
        hovertemplate="Lower: $%{y:.2f}<extra></extra>",
    ))

    # ── Predicted price line ──────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=dates,
        y=predicted,
        mode="lines+markers",
        line=dict(color=line_color, width=2.5),
        marker=dict(size=6, color=line_color),
        name="Predicted Price",
        hovertemplate="Date: %{x}<br>Predicted: $%{y:.2f}<extra></extra>",
    ))

    # ── Current price reference line ──────────────────────────────
    if current_price:
        fig.add_hline(
            y=current_price,
            line_dash="dash",
            line_color="rgba(255,255,255,0.3)",
            line_width=1,
            annotation_text=f"  Current ${current_price:.2f}",
            annotation_font_color="rgba(255,255,255,0.4)",
            annotation_font_size=11,
        )

    # ── Chart layout ──────────────────────────────────────────────
    fig.update_layout(
        title=dict(
            text=f"{ticker} — 7-Day Price Forecast",
            font=dict(size=16, color="#f1f5f9"),
            x=0,
        ),
        paper_bgcolor="#1a1d27",
        plot_bgcolor="#1a1d27",
        font=dict(color="#94a3b8", size=12),
        xaxis=dict(
            gridcolor="#2d3748",
            tickfont=dict(color="#64748b"),
            showline=False,
        ),
        yaxis=dict(
            gridcolor="#2d3748",
            tickfont=dict(color="#64748b"),
            tickprefix="$",
            showline=False,
        ),
        legend=dict(
            font=dict(color="#94a3b8", size=11),
            bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(l=10, r=10, t=50, b=10),
        height=320,
        hovermode="x unified",
    )

    st.plotly_chart(fig, use_container_width=True)