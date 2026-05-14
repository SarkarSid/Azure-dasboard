"""
Interactive chatbot grounded on the live dashboard context.
Uses Azure OpenAI via Managed Identity (no API keys).
"""
from __future__ import annotations

import json
from typing import Iterator

import pandas as pd
import streamlit as st

from config import AZURE_CFG
from modules.aoai_client import get_aoai_client


SYSTEM_PROMPT = """You are an Azure Cost & Governance Assistant for a Principal Cloud Solution Engineer.

You have real-time visibility into the user's Azure environment via the DASHBOARD CONTEXT below.

Your responsibilities:
1. Answer questions about costs, advisor recommendations, and security alerts using ONLY the dashboard context. If something isn't in the context, say so honestly and tell them which dashboard tab to check.
2. Provide actionable, prioritised recommendations.
3. Keep answers concise — 3 to 6 sentences unless the user asks for detail.
4. Quantify impact when possible (savings in $, severity counts, % of total spend).
5. Reference specific resource groups, services, and alerts by name.

Formatting:
- Use bullet points for lists of recommendations.
- Use **bold** for key numbers and resource names.
- Use markdown headings (###) only for multi-section answers."""


SUGGESTIONS = [
    "What are my top 3 cost optimisation opportunities right now?",
    "Which security alerts need immediate attention and why?",
    "Why is my Databricks spend so high — what can I do about it?",
    "How can I reduce data transmission / egress costs?",
]


def build_context(
    selected_rgs: list[str],
    selected_rg: str,
    df_rg_summary: pd.DataFrame,
    df_service: pd.DataFrame,
    df_tx: pd.DataFrame,
    df_recs: pd.DataFrame,
    df_alerts: pd.DataFrame,
    secure_score: float,
) -> str:
    """Serialise current dashboard state into a compact JSON context block."""
    rg_costs = (
        df_rg_summary.head(15).to_dict("records") if not df_rg_summary.empty else []
    )

    services = []
    if not df_service.empty:
        for _, row in df_service.head(15).iterrows():
            services.append({
                "service": row.get("ServiceLabel", row.get("ServiceName", "")),
                "cost_usd": round(float(row.get("Cost", 0)), 2),
            })

    transmission = {}
    if not df_tx.empty:
        transmission = {
            "egress_total_usd": round(float(df_tx["EgressCost"].sum()), 2),
            "ingress_total_usd": round(float(df_tx["IngressCost"].sum()), 2),
            "inter_region_total_usd": round(float(df_tx["InterRegionCost"].sum()), 2),
        }

    advisor = {"by_category": [], "top_savings_opportunities": []}
    if not df_recs.empty:
        for cat in sorted(df_recs["Category"].unique()):
            sub = df_recs[df_recs["Category"] == cat]
            advisor["by_category"].append({
                "category": cat,
                "high": int((sub["Impact"] == "High").sum()),
                "medium": int((sub["Impact"] == "Medium").sum()),
                "low": int((sub["Impact"] == "Low").sum()),
                "monthly_savings_usd": round(float(sub["PotentialSavings"].sum()), 2),
            })
        top = df_recs.sort_values("PotentialSavings", ascending=False).head(5)
        advisor["top_savings_opportunities"] = [
            {
                "category": r["Category"],
                "impact": r["Impact"],
                "resource_group": r["ResourceGroup"],
                "resource": r["ResourceName"],
                "problem": r["ShortDescription"],
                "monthly_savings_usd": round(float(r["PotentialSavings"]), 2),
            }
            for _, r in top.iterrows()
        ]

    security = {
        "secure_score": secure_score,
        "high": 0, "medium": 0, "low": 0, "active": 0,
        "high_severity_alerts": [],
    }
    if not df_alerts.empty:
        security["high"] = int((df_alerts["Severity"] == "High").sum())
        security["medium"] = int((df_alerts["Severity"] == "Medium").sum())
        security["low"] = int((df_alerts["Severity"] == "Low").sum())
        security["active"] = int((df_alerts["Status"] == "Active").sum())
        high_alerts = df_alerts[df_alerts["Severity"] == "High"].head(5)
        security["high_severity_alerts"] = [
            {
                "type": r["AlertType"],
                "resource_group": r["ResourceGroup"],
                "resource": r["ResourceName"],
                "description": r["Description"],
                "remediation": r.get("Remediation", ""),
            }
            for _, r in high_alerts.iterrows()
        ]

    context = {
        "selected_resource_groups": selected_rgs,
        "drill_down_resource_group": selected_rg,
        "monthly_cost_by_resource_group": rg_costs,
        f"top_services_in_{selected_rg}": services,
        "data_transmission_costs": transmission,
        "advisor": advisor,
        "security": security,
    }
    return f"DASHBOARD CONTEXT:\n```json\n{json.dumps(context, indent=2, default=str)}\n```"


def _stream(client, deployment: str, messages: list[dict]) -> Iterator[str]:
    stream = client.chat.completions.create(
        model=deployment,
        messages=messages,
        max_tokens=900,
        temperature=0.3,
        stream=True,
    )
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def render_chat_ui(context_str: str):
    """Render the chat panel — chat history, suggestions, input box."""
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    if not AZURE_CFG.aoai_enabled:
        st.info(
            "Chat assistant is disabled. Set `AZURE_OPENAI_ENDPOINT` and "
            "`AZURE_OPENAI_DEPLOYMENT` in `.env` and grant the Web App's "
            "Managed Identity the **Cognitive Services OpenAI User** role.",
            icon="🤖",
        )
        return

    client = get_aoai_client()
    if client is None:
        st.error("Azure OpenAI client could not be initialised. Check Managed Identity RBAC.")
        return

    # Header card
    st.markdown(
        """
        <div style="background:linear-gradient(135deg,#0078d4 0%,#005a9e 100%);
             color:white;padding:16px 22px;border-radius:10px;margin-bottom:16px;">
            <div style="font-size:18px;font-weight:700;">🤖 Azure Cloud Assistant</div>
            <div style="font-size:13px;opacity:0.9;margin-top:4px;">
                Grounded on your live dashboard data. Powered by Azure OpenAI via Managed Identity.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Suggestion chips — only when there's no chat yet
    if not st.session_state.chat_history:
        st.markdown("**💡 Try asking:**")
        cols = st.columns(2)
        for i, suggestion in enumerate(SUGGESTIONS):
            if cols[i % 2].button(suggestion, key=f"sug_{i}", use_container_width=True):
                st.session_state.pending_chat = suggestion
                st.rerun()

    # Render history
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Resolve next user message (suggestion click or chat input)
    user_msg = st.session_state.pop("pending_chat", None)
    if not user_msg:
        user_msg = st.chat_input("Ask anything about your Azure costs, security, or governance...")

    if not user_msg:
        return

    st.session_state.chat_history.append({"role": "user", "content": user_msg})
    with st.chat_message("user"):
        st.markdown(user_msg)

    messages = (
        [{"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{context_str}"}]
        + [{"role": m["role"], "content": m["content"]} for m in st.session_state.chat_history]
    )

    with st.chat_message("assistant"):
        placeholder = st.empty()
        full = ""
        try:
            for token in _stream(client, AZURE_CFG.aoai_deployment, messages):
                full += token
                placeholder.markdown(full + "▌")
            placeholder.markdown(full)
        except Exception as exc:
            full = f"⚠️ Assistant error: `{exc}`"
            placeholder.markdown(full)

    st.session_state.chat_history.append({"role": "assistant", "content": full})


def render_clear_button():
    if st.session_state.get("chat_history"):
        col1, col2 = st.columns([6, 1])
        with col2:
            if st.button("🗑️ Clear", use_container_width=True, key="clear_chat"):
                st.session_state.chat_history = []
                st.rerun()
