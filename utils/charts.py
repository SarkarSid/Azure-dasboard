"""
Chart builders using Altair (bundled with Streamlit) — no plotly dependency.
"""
from __future__ import annotations

import altair as alt
import pandas as pd

from config import SERVICE_ICONS, ADVISOR_CATEGORY_COLORS

AZURE_BLUE = "#0078d4"
PALETTE = [
    "#0078d4", "#50e6ff", "#6264a7", "#e74c3c",
    "#2ecc71", "#f39c12", "#9b59b6", "#1abc9c",
    "#e84855", "#3d85c8", "#6aa84f", "#f7c59f",
]


def cost_trend_chart(df: pd.DataFrame, group_col: str = "ServiceName") -> alt.Chart:
    """Stacked area — daily cost per service over time."""
    return (
        alt.Chart(df)
        .mark_area(opacity=0.85, interpolate="monotone")
        .encode(
            x=alt.X("Date:T", title=None),
            y=alt.Y("Cost:Q", title="Cost (USD)", stack="zero"),
            color=alt.Color(
                f"{group_col}:N",
                scale=alt.Scale(range=PALETTE),
                legend=alt.Legend(orient="top", title=None, columns=4),
            ),
            tooltip=[
                alt.Tooltip("Date:T", title="Date"),
                alt.Tooltip(f"{group_col}:N", title="Service"),
                alt.Tooltip("Cost:Q", title="Cost", format="$,.2f"),
            ],
        )
        .properties(height=320, title="Daily Cost Trend by Service")
        .configure_view(strokeWidth=0)
    )


def cost_donut_chart(df: pd.DataFrame, label_col: str, value_col: str, title: str) -> alt.Chart:
    """Donut chart for cost distribution."""
    df_local = df.copy()
    df_local["DisplayLabel"] = df_local[label_col].map(
        lambda x: f"{SERVICE_ICONS.get(x, '')} {x}".strip()
    )

    base = alt.Chart(df_local).encode(
        theta=alt.Theta(field=value_col, type="quantitative", stack=True),
        color=alt.Color(
            "DisplayLabel:N",
            scale=alt.Scale(range=PALETTE),
            legend=alt.Legend(orient="right", title=None, labelFontSize=11),
        ),
        tooltip=[
            alt.Tooltip("DisplayLabel:N", title="Service"),
            alt.Tooltip(f"{value_col}:Q", title="Cost", format="$,.2f"),
        ],
    )
    arc = base.mark_arc(innerRadius=70, outerRadius=130, stroke="#fff", strokeWidth=2)
    return arc.properties(height=320, title=title).configure_view(strokeWidth=0)


def resource_group_bar(df: pd.DataFrame) -> alt.Chart:
    """Horizontal bar — cost per resource group."""
    return (
        alt.Chart(df)
        .mark_bar(color=AZURE_BLUE, cornerRadius=4)
        .encode(
            x=alt.X("Cost:Q", title="Cost (USD)"),
            y=alt.Y("ResourceGroup:N", sort="-x", title=None),
            tooltip=[
                alt.Tooltip("ResourceGroup:N", title="Resource Group"),
                alt.Tooltip("Cost:Q", title="Cost", format="$,.2f"),
            ],
        )
        .properties(height=max(60, 32 * len(df)), title="Cost by Resource Group")
        .configure_view(strokeWidth=0)
    )


def transmission_cost_chart(df: pd.DataFrame) -> alt.Chart:
    """Stacked bar — egress / ingress / inter-region by date."""
    long_df = df.melt(
        id_vars="Date",
        value_vars=["EgressCost", "IngressCost", "InterRegionCost"],
        var_name="Direction",
        value_name="Cost",
    )
    label_map = {
        "EgressCost": "Egress (Internet)",
        "IngressCost": "Ingress",
        "InterRegionCost": "Inter-Region",
    }
    long_df["Direction"] = long_df["Direction"].map(label_map)
    color_map = {
        "Egress (Internet)": "#e84855",
        "Ingress": "#2ecc71",
        "Inter-Region": "#f39c12",
    }
    return (
        alt.Chart(long_df)
        .mark_bar()
        .encode(
            x=alt.X("Date:T", title=None),
            y=alt.Y("Cost:Q", title="Cost (USD)", stack="zero"),
            color=alt.Color(
                "Direction:N",
                scale=alt.Scale(
                    domain=list(color_map.keys()),
                    range=list(color_map.values()),
                ),
                legend=alt.Legend(orient="top", title=None),
            ),
            tooltip=[
                alt.Tooltip("Date:T"),
                alt.Tooltip("Direction:N"),
                alt.Tooltip("Cost:Q", format="$,.2f"),
            ],
        )
        .properties(height=300, title="Data Transmission Costs")
        .configure_view(strokeWidth=0)
    )


def advisor_category_bar(df: pd.DataFrame) -> alt.Chart:
    """Horizontal bar — recommendation count by category."""
    counts = df.groupby("Category").size().reset_index(name="Count")
    return (
        alt.Chart(counts)
        .mark_bar(cornerRadius=4)
        .encode(
            x=alt.X("Count:Q", title="Count"),
            y=alt.Y("Category:N", sort="-x", title=None),
            color=alt.Color(
                "Category:N",
                scale=alt.Scale(
                    domain=list(ADVISOR_CATEGORY_COLORS.keys()),
                    range=list(ADVISOR_CATEGORY_COLORS.values()),
                ),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("Category:N"),
                alt.Tooltip("Count:Q"),
            ],
        )
        .properties(
            height=max(120, 36 * len(counts)),
            title="Advisor Recommendations by Category",
        )
        .configure_view(strokeWidth=0)
    )


def cost_forecast_chart(df_actual: pd.DataFrame, df_forecast: pd.DataFrame) -> alt.Chart:
    """Line chart overlaying actuals + projected cumulative cost."""
    actual = df_actual.assign(Series="Actual (MTD)")
    if df_forecast is not None and not df_forecast.empty:
        forecast = df_forecast.assign(Series="Forecast")
        combined = pd.concat([actual, forecast], ignore_index=True)
    else:
        combined = actual

    return (
        alt.Chart(combined)
        .mark_line(point=True, strokeWidth=3)
        .encode(
            x=alt.X("Date:T", title=None),
            y=alt.Y("CumulativeCost:Q", title="Cumulative Cost (USD)"),
            color=alt.Color(
                "Series:N",
                scale=alt.Scale(
                    domain=["Actual (MTD)", "Forecast"],
                    range=[AZURE_BLUE, "#f39c12"],
                ),
                legend=alt.Legend(orient="top", title=None),
            ),
            strokeDash=alt.condition(
                alt.datum.Series == "Forecast",
                alt.value([6, 4]),
                alt.value([0]),
            ),
            tooltip=[
                alt.Tooltip("Date:T"),
                alt.Tooltip("Series:N"),
                alt.Tooltip("CumulativeCost:Q", format="$,.2f"),
            ],
        )
        .properties(height=300, title="Monthly Cost — Actual vs Forecast")
        .configure_view(strokeWidth=0)
    )


def severity_distribution_html(high: int, medium: int, low: int) -> str:
    """Return HTML markup showing severity counts as colored cards."""
    cards = [
        ("High", high, "#e84855"),
        ("Medium", medium, "#f7c59f"),
        ("Low", low, "#6aa84f"),
    ]
    items = "".join(
        f"""
        <div style="flex:1;text-align:center;padding:14px;background:white;
             border:1px solid #eee;border-radius:8px;
             border-top:4px solid {color};box-shadow:0 1px 4px rgba(0,0,0,0.05);">
            <div style="font-size:11px;color:#666;text-transform:uppercase;
                 letter-spacing:0.5px;font-weight:600;">{label}</div>
            <div style="font-size:34px;font-weight:800;color:{color};
                 line-height:1.1;margin-top:4px;">{count}</div>
        </div>
        """
        for label, count, color in cards
    )
    return f'<div style="display:flex;gap:10px;margin:8px 0;">{items}</div>'
