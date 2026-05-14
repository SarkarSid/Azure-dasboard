from __future__ import annotations

import json
import streamlit as st

from config import AZURE_CFG
from modules.aoai_client import get_aoai_client


def cost_narrative(cost_summary: dict, resource_group: str) -> str:
    """Generate a short executive cost commentary from cost data."""
    client = get_aoai_client()
    if client is None:
        return ""

    prompt = (
        f"You are a Principal Cloud Solution Engineer reviewing Azure costs for resource group '{resource_group}'.\n"
        f"Given the following monthly cost breakdown (USD):\n{json.dumps(cost_summary, indent=2)}\n\n"
        "Write a concise 3-5 sentence executive summary that:\n"
        "1. Identifies the top cost drivers.\n"
        "2. Highlights any unusual spend patterns.\n"
        "3. Gives 2 concrete, actionable optimisation recommendations.\n"
        "Be direct, data-driven, and avoid filler text."
    )
    try:
        response = client.chat.completions.create(
            model=AZURE_CFG.aoai_deployment,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        return f"AI insights unavailable: {exc}"


def advisor_summary(recommendations_df, security_df) -> str:
    """Synthesise advisor + security data into a governance brief."""
    client = get_aoai_client()
    if client is None:
        return ""

    rec_summary = (
        recommendations_df.groupby(["Category", "Impact"]).size()
        .reset_index(name="Count").to_dict("records")
    )
    sec_summary = (
        security_df.groupby(["Severity", "Status"]).size()
        .reset_index(name="Count").to_dict("records")
    )
    savings = float(recommendations_df["PotentialSavings"].sum())

    prompt = (
        "You are a Principal Cloud Solution Engineer writing a governance brief.\n"
        f"Azure Advisor recommendation breakdown: {json.dumps(rec_summary)}\n"
        f"Security alert breakdown: {json.dumps(sec_summary)}\n"
        f"Total potential savings identified: ${savings:,.2f}/month\n\n"
        "Write a 3-4 sentence governance summary that:\n"
        "1. Calls out the most urgent actions (high-severity security + reliability).\n"
        "2. Quantifies the cost-saving opportunity.\n"
        "3. Recommends a prioritisation order.\n"
        "Be concise and actionable."
    )
    try:
        response = client.chat.completions.create(
            model=AZURE_CFG.aoai_deployment,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=350,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        return f"AI insights unavailable: {exc}"


def render_ai_insight_block(title: str, content: str):
    if not content:
        return
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, #e8f4fd 0%, #f0f8ff 100%);
            border-left: 4px solid #0078d4;
            border-radius: 8px;
            padding: 16px 20px;
            margin: 12px 0;
        ">
            <div style="font-size:13px;font-weight:600;color:#0078d4;margin-bottom:6px;">
                🤖 {title}
            </div>
            <div style="font-size:14px;color:#323130;line-height:1.6;">{content}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
