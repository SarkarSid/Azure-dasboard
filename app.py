"""
Azure Cost & Governance Dashboard
Principal Cloud Solution Engineer view — resource-group-wise cost overview,
real-time usage, data transmission costs, Advisor recommendations, and
Defender for Cloud security alerts.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from config import APP_CFG, AZURE_CFG, ADVISOR_SEVERITY_COLORS
from modules.azure_cost import AzureCostManager
from modules.azure_advisor import AzureAdvisorManager
from modules.ai_insights import cost_narrative, advisor_summary, render_ai_insight_block
from modules.chat_assistant import build_context, render_chat_ui, render_clear_button
from utils.formatters import fmt_currency, fmt_delta, date_range, severity_badge, category_badge
from utils.charts import (
    cost_trend_chart,
    cost_donut_chart,
    resource_group_bar,
    transmission_cost_chart,
    cost_forecast_chart,
    advisor_category_bar,
    severity_distribution_html,
)

# ─── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Azure Cost & Governance Dashboard",
    page_icon="☁️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ───────────────────────────────────────────────────────────────

st.markdown("""
<style>
    /* Sidebar */
    [data-testid="stSidebar"] { background: #1a1a2e; }
    [data-testid="stSidebar"] * { color: #e0e0e0 !important; }
    [data-testid="stSidebar"] .stSelectbox label,
    [data-testid="stSidebar"] .stMultiSelect label,
    [data-testid="stSidebar"] .stSlider label { color: #90caf9 !important; font-weight: 600; }

    /* Metric cards */
    div[data-testid="metric-container"] {
        background: #ffffff;
        border: 1px solid #e8e8e8;
        border-radius: 10px;
        padding: 18px 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }
    div[data-testid="metric-container"] label { font-size: 12px !important; color: #666 !important; }
    div[data-testid="metric-container"] [data-testid="stMetricValue"] {
        font-size: 28px !important; font-weight: 700 !important; color: #0078d4 !important;
    }

    /* Section headers */
    .section-header {
        font-size: 16px; font-weight: 700; color: #1a1a2e;
        border-bottom: 2px solid #0078d4;
        padding-bottom: 6px; margin: 20px 0 14px 0;
    }

    /* Status badges */
    .badge-high { background: #fde8e8; color: #c0392b; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }
    .badge-medium { background: #fef9e7; color: #b7950b; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }
    .badge-low { background: #e9f7ef; color: #1e8449; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }

    /* Demo banner */
    .demo-banner {
        background: linear-gradient(90deg, #ff6b35, #f7c59f);
        color: white; padding: 10px 20px; border-radius: 8px;
        font-weight: 600; font-size: 14px; margin-bottom: 16px;
        text-align: center;
    }

    /* Live indicator */
    .live-dot { display: inline-block; width: 8px; height: 8px;
        background: #2ecc71; border-radius: 50%; margin-right: 6px;
        animation: pulse 1.5s infinite; }
    @keyframes pulse {
        0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; }
    }

    /* Table styling */
    .dataframe { font-size: 13px !important; }
    .stDataFrame { border-radius: 8px; overflow: hidden; }

    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        background: #f0f2f6; border-radius: 8px 8px 0 0;
        padding: 8px 20px; font-weight: 600; font-size: 14px;
    }
    .stTabs [aria-selected="true"] {
        background: #0078d4 !important; color: white !important;
    }

    /* Expander */
    .streamlit-expanderHeader { font-weight: 600; font-size: 14px; }
</style>
""", unsafe_allow_html=True)

# ─── Initialise managers ──────────────────────────────────────────────────────

@st.cache_resource
def get_cost_manager() -> AzureCostManager:
    return AzureCostManager()

@st.cache_resource
def get_advisor_manager() -> AzureAdvisorManager:
    return AzureAdvisorManager()

cost_mgr = get_cost_manager()
adv_mgr = get_advisor_manager()

is_demo = not cost_mgr.live
last_refresh = st.session_state.get("last_refresh", datetime.utcnow())

# ─── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## ☁️ Azure Dashboard")
    st.markdown("---")

    resource_groups = cost_mgr.list_resource_groups()
    selected_rgs = st.multiselect(
        "Resource Groups",
        options=resource_groups,
        default=resource_groups[:3] if len(resource_groups) > 3 else resource_groups,
        help="Filter by resource group(s). Leave empty to show all.",
    )
    if not selected_rgs:
        selected_rgs = resource_groups

    selected_rg = st.selectbox(
        "Drill-down Resource Group",
        options=selected_rgs,
        help="Detailed breakdown for a single resource group.",
    )

    st.markdown("---")
    lookback_days = st.slider(
        "Lookback Period (days)",
        min_value=7, max_value=90,
        value=APP_CFG.default_lookback_days,
        step=7,
    )

    currency = st.selectbox("Currency", ["USD", "EUR", "GBP"], index=0)
    st.markdown("---")

    if st.button("🔄 Refresh Data", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.session_state["last_refresh"] = datetime.utcnow()
        st.rerun()
    st.caption("Data is cached for 5 min. Click to force-refresh.")

    st.markdown("---")
    auth_mode = (
        "Managed Identity" if AZURE_CFG.is_configured and not APP_CFG.demo_mode
        else "Demo"
    )
    st.markdown(f"**Auth:** {auth_mode}")
    if AZURE_CFG.is_configured:
        st.markdown(f"**Subscription:** `{AZURE_CFG.subscription_id[:8]}…`")
    if AZURE_CFG.aoai_enabled:
        st.markdown(
            f"**AOAI:** `{AZURE_CFG.aoai_deployment}` "
            f"<span class='live-dot'></span>",
            unsafe_allow_html=True,
        )
    elapsed = int((datetime.utcnow() - last_refresh).total_seconds())
    st.caption(f"Last refresh: {elapsed}s ago")

# ─── Header ───────────────────────────────────────────────────────────────────

col_title, col_ts = st.columns([4, 1])
with col_title:
    st.markdown("# Azure Cost & Governance Dashboard")
    if is_demo:
        st.markdown(
            '<div class="demo-banner">⚠️ DEMO MODE — Configure Azure credentials in .env to connect live data</div>',
            unsafe_allow_html=True,
        )
with col_ts:
    st.markdown(f"**{datetime.utcnow().strftime('%d %b %Y %H:%M')} UTC**")

# ─── Tabs ─────────────────────────────────────────────────────────────────────

tab_cost, tab_advisor, tab_security, tab_chat = st.tabs([
    "💰 Cost Overview",
    "📋 Azure Advisor",
    "🔐 Security & Compliance",
    "💬 AI Assistant",
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — COST OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════════

with tab_cost:
    start_date, end_date = date_range(lookback_days)

    # Load data
    with st.spinner("Fetching cost data..."):
        df_rg_summary = cost_mgr.all_rg_cost_summary(selected_rgs, start_date, end_date)
        df_service = cost_mgr.cost_by_service(selected_rg, start_date, end_date)
        df_trend = cost_mgr.daily_cost_trend(selected_rg, start_date, end_date)
        df_tx = cost_mgr.data_transmission_costs(selected_rg, start_date, end_date)

    # ── KPI row ──────────────────────────────────────────────────────────────
    total_cost = df_service["Cost"].sum()
    total_tx = (
        df_tx[["EgressCost", "IngressCost", "InterRegionCost"]].sum().sum()
        if not df_tx.empty else 0
    )
    daily_avg = total_cost / max(lookback_days, 1)
    projected_eom = daily_avg * 30
    top_service = df_service.iloc[0]["ServiceLabel"] if not df_service.empty else "N/A"
    top_service_cost = df_service.iloc[0]["Cost"] if not df_service.empty else 0

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric(
        f"Total Cost ({lookback_days}d)",
        fmt_currency(total_cost),
        help="All services in selected resource group",
    )
    k2.metric(
        "Daily Burn Rate",
        fmt_currency(daily_avg),
        help="Average daily spend over the period",
    )
    k3.metric(
        "Projected Monthly",
        fmt_currency(projected_eom),
        help="Extrapolated to 30 days at current rate",
    )
    k4.metric(
        "Data Transfer Costs",
        fmt_currency(total_tx),
        help="Egress + Ingress + Inter-region bandwidth",
    )
    k5.metric(
        "Top Service",
        top_service,
        delta=fmt_currency(top_service_cost),
        delta_color="off",
    )

    st.markdown("---")

    # ── All-RG overview ───────────────────────────────────────────────────────
    st.markdown('<div class="section-header">Resource Group Cost Summary</div>', unsafe_allow_html=True)

    col_bar, col_table = st.columns([3, 2])
    with col_bar:
        if not df_rg_summary.empty:
            st.altair_chart(resource_group_bar(df_rg_summary), use_container_width=True)

    with col_table:
        st.markdown(f"**Showing {len(df_rg_summary)} resource group(s)**")
        display_rg = df_rg_summary.copy()
        display_rg["Cost"] = display_rg["Cost"].apply(fmt_currency)
        st.dataframe(display_rg, use_container_width=True, hide_index=True)

    # ── Per-RG drill-down ─────────────────────────────────────────────────────
    st.markdown(
        f'<div class="section-header">Service Breakdown — {selected_rg}</div>',
        unsafe_allow_html=True,
    )

    col_donut, col_svc_table = st.columns([2, 3])
    with col_donut:
        if not df_service.empty:
            st.altair_chart(
                cost_donut_chart(df_service, "ServiceLabel", "Cost", "Cost by Service"),
                use_container_width=True,
            )

    with col_svc_table:
        if not df_service.empty:
            tbl = df_service[["ServiceLabel", "Cost", "Currency"]].copy()
            tbl = tbl.sort_values("Cost", ascending=False)
            tbl["Share %"] = (tbl["Cost"] / tbl["Cost"].sum() * 100).round(1)
            tbl["Cost"] = tbl["Cost"].apply(fmt_currency)
            tbl = tbl.rename(columns={"ServiceLabel": "Service"})
            st.dataframe(tbl, use_container_width=True, hide_index=True)

            csv = df_service.to_csv(index=False).encode()
            st.download_button(
                "⬇️ Export to CSV",
                csv,
                file_name=f"{selected_rg}_costs_{end_date}.csv",
                mime="text/csv",
            )

    # ── Cost trend ────────────────────────────────────────────────────────────
    st.markdown('<div class="section-header">Daily Cost Trend</div>', unsafe_allow_html=True)

    if not df_trend.empty:
        st.altair_chart(cost_trend_chart(df_trend), use_container_width=True)

    # ── Forecast ──────────────────────────────────────────────────────────────
    with st.expander("📈 Month-to-Date vs Forecast", expanded=False):
        if not df_trend.empty:
            daily_totals = df_trend.groupby("Date")["Cost"].sum().reset_index()
            daily_totals = daily_totals.sort_values("Date")
            daily_totals["CumulativeCost"] = daily_totals["Cost"].cumsum()

            today = datetime.utcnow().date()
            end_of_month = (today.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            remaining_days = (end_of_month - today).days

            if remaining_days > 0:
                avg_daily = daily_totals["Cost"].mean()
                last_cum = daily_totals["CumulativeCost"].iloc[-1]
                forecast_rows = []
                for i in range(1, remaining_days + 1):
                    forecast_rows.append({
                        "Date": pd.Timestamp(today) + timedelta(days=i),
                        "CumulativeCost": last_cum + avg_daily * i,
                    })
                df_forecast = pd.DataFrame(forecast_rows)
            else:
                df_forecast = pd.DataFrame()

            st.altair_chart(
                cost_forecast_chart(daily_totals, df_forecast),
                use_container_width=True,
            )

    # ── Data transmission ──────────────────────────────────────────────────────
    st.markdown('<div class="section-header">Data Transmission Costs</div>', unsafe_allow_html=True)

    tx_col1, tx_col2 = st.columns([3, 1])
    with tx_col1:
        if not df_tx.empty:
            st.altair_chart(transmission_cost_chart(df_tx), use_container_width=True)

    with tx_col2:
        if not df_tx.empty:
            total_egress = df_tx["EgressCost"].sum()
            total_ingress = df_tx["IngressCost"].sum()
            total_inter = df_tx["InterRegionCost"].sum()
            st.metric("Egress (Internet)", fmt_currency(total_egress))
            st.metric("Ingress", fmt_currency(total_ingress))
            st.metric("Inter-Region", fmt_currency(total_inter))
            st.metric("Total Bandwidth", fmt_currency(total_egress + total_ingress + total_inter))
            st.caption("Tip: Use Private Endpoints to eliminate egress charges.")

    # ── AI Cost Insights ──────────────────────────────────────────────────────
    if AZURE_CFG.aoai_enabled and not df_service.empty:
        with st.expander("🤖 AI Cost Insights (Azure OpenAI)", expanded=True):
            cost_summary = {
                row["ServiceLabel"]: round(row["Cost"], 2)
                for _, row in df_service.iterrows()
            }
            with st.spinner("Generating AI insights..."):
                narrative = cost_narrative(cost_summary, selected_rg)
            render_ai_insight_block("Executive Cost Commentary", narrative)
    elif not AZURE_CFG.aoai_enabled:
        st.info(
            "Set `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_DEPLOYMENT` in `.env` "
            "to enable AI insights (Managed Identity — no API key needed).",
            icon="🤖",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — AZURE ADVISOR
# ═══════════════════════════════════════════════════════════════════════════════

with tab_advisor:
    with st.spinner("Fetching Advisor recommendations..."):
        df_recs = adv_mgr.recommendations(selected_rgs)

    if df_recs.empty:
        st.info("No Advisor recommendations found for selected resource groups.")
    else:
        # ── Summary KPIs ──────────────────────────────────────────────────────
        total_savings = df_recs["PotentialSavings"].sum()
        high_count = len(df_recs[df_recs["Impact"] == "High"])
        medium_count = len(df_recs[df_recs["Impact"] == "Medium"])
        low_count = len(df_recs[df_recs["Impact"] == "Low"])
        cost_recs = df_recs[df_recs["Category"] == "Cost"]

        a1, a2, a3, a4, a5 = st.columns(5)
        a1.metric("Total Recommendations", len(df_recs))
        a2.metric("High Impact", high_count, help="Immediate action recommended")
        a3.metric("Medium Impact", medium_count)
        a4.metric("Low Impact", low_count)
        a5.metric("Potential Savings/mo", fmt_currency(total_savings), help="From cost-category recommendations")

        st.markdown("---")

        # ── Filters ───────────────────────────────────────────────────────────
        fcol1, fcol2, fcol3 = st.columns(3)
        with fcol1:
            cat_filter = st.multiselect(
                "Filter by Category",
                options=sorted(df_recs["Category"].unique()),
                default=[],
                key="adv_cat",
            )
        with fcol2:
            impact_filter = st.multiselect(
                "Filter by Impact",
                options=["High", "Medium", "Low"],
                default=["High", "Medium"],
                key="adv_impact",
            )
        with fcol3:
            rg_filter = st.multiselect(
                "Filter by Resource Group",
                options=sorted(df_recs["ResourceGroup"].unique()),
                default=[],
                key="adv_rg",
            )

        filtered = df_recs.copy()
        if cat_filter:
            filtered = filtered[filtered["Category"].isin(cat_filter)]
        if impact_filter:
            filtered = filtered[filtered["Impact"].isin(impact_filter)]
        if rg_filter:
            filtered = filtered[filtered["ResourceGroup"].isin(rg_filter)]

        # ── Charts ────────────────────────────────────────────────────────────
        chart_col, dist_col = st.columns([3, 2])
        with chart_col:
            st.altair_chart(advisor_category_bar(filtered), use_container_width=True)

        with dist_col:
            st.markdown('<div class="section-header">Impact Distribution</div>', unsafe_allow_html=True)
            for impact, color in [("High", "#e84855"), ("Medium", "#f7c59f"), ("Low", "#2ecc71")]:
                cnt = len(filtered[filtered["Impact"] == impact])
                bar_pct = int(cnt / max(len(filtered), 1) * 100)
                st.markdown(
                    f"""
                    <div style="margin:6px 0;">
                        <span style="font-size:13px;font-weight:600;color:{color};">{impact}</span>
                        <span style="float:right;font-size:13px;">{cnt}</span>
                        <div style="background:#f0f0f0;border-radius:4px;height:8px;margin-top:4px;">
                            <div style="background:{color};width:{bar_pct}%;height:8px;border-radius:4px;"></div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        # ── Recommendation cards ──────────────────────────────────────────────
        st.markdown('<div class="section-header">Recommendations</div>', unsafe_allow_html=True)

        filtered_sorted = filtered.sort_values(
            by=["Impact", "PotentialSavings"],
            key=lambda col: col.map({"High": 0, "Medium": 1, "Low": 2}) if col.name == "Impact" else col,
            ascending=[True, False],
        )

        for _, row in filtered_sorted.iterrows():
            badge_class = f"badge-{row['Impact'].lower()}"
            savings_str = f"  |  💰 Saves ~{fmt_currency(row['PotentialSavings'])}/mo" if row["PotentialSavings"] > 0 else ""
            with st.expander(
                f"{category_badge(row['Category'])} {row['ShortDescription'][:90]}  "
                f"[{row['ResourceGroup']} / {row['ResourceName']}]",
                expanded=row["Impact"] == "High",
            ):
                c1, c2, c3 = st.columns([2, 2, 1])
                c1.markdown(f"**Category:** {row['Category']}")
                c2.markdown(f"**Resource:** `{row['ResourceName']}`")
                c3.markdown(
                    f'<span class="{badge_class}">{severity_badge(row["Impact"])} {row["Impact"]}</span>{savings_str}',
                    unsafe_allow_html=True,
                )
                st.markdown(f"**Problem:** {row['ShortDescription']}")
                st.markdown(f"**Recommended Action:** {row['Solution']}")
                st.caption(f"Resource Group: {row['ResourceGroup']} | Last Updated: {row['LastUpdated']}")

    # ── AI Governance Summary ─────────────────────────────────────────────────
    if AZURE_CFG.aoai_enabled and not df_recs.empty:
        with st.expander("🤖 AI Governance Brief", expanded=True):
            df_sec_for_ai = adv_mgr.security_alerts(selected_rgs)
            with st.spinner("Generating governance summary..."):
                brief = advisor_summary(df_recs, df_sec_for_ai)
            render_ai_insight_block("Governance Brief", brief)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — SECURITY & COMPLIANCE
# ═══════════════════════════════════════════════════════════════════════════════

with tab_security:
    with st.spinner("Fetching security data..."):
        df_alerts = adv_mgr.security_alerts(selected_rgs)
        secure_score = adv_mgr.secure_score()

    # ── Secure Score ──────────────────────────────────────────────────────────
    sc1, sc2, sc3, sc4 = st.columns(4)
    score_color = "#2ecc71" if secure_score >= 70 else ("#f7c59f" if secure_score >= 50 else "#e84855")
    sc1.markdown(
        f"""
        <div style="background:white;border:1px solid #e8e8e8;border-radius:10px;padding:20px;
             box-shadow:0 2px 8px rgba(0,0,0,0.06);text-align:center;">
            <div style="font-size:12px;color:#666;margin-bottom:4px;">Secure Score</div>
            <div style="font-size:48px;font-weight:800;color:{score_color};">{secure_score:.0f}</div>
            <div style="font-size:12px;color:#999;">/ 100</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not df_alerts.empty:
        high_alerts = len(df_alerts[df_alerts["Severity"] == "High"])
        med_alerts = len(df_alerts[df_alerts["Severity"] == "Medium"])
        low_alerts = len(df_alerts[df_alerts["Severity"] == "Low"])
        active_alerts = len(df_alerts[df_alerts["Status"] == "Active"])
    else:
        high_alerts = med_alerts = low_alerts = active_alerts = 0

    sc2.metric("🔴 High Severity", high_alerts, help="Requires immediate attention")
    sc3.metric("🟡 Medium Severity", med_alerts)
    sc4.metric("Active Alerts", active_alerts, help="Non-dismissed alerts requiring action")

    st.markdown("---")

    if not df_alerts.empty:
        # ── Filters ───────────────────────────────────────────────────────────
        sf1, sf2, sf3 = st.columns(3)
        with sf1:
            sev_filter = st.multiselect(
                "Severity",
                options=["High", "Medium", "Low"],
                default=["High", "Medium"],
                key="sec_sev",
            )
        with sf2:
            status_filter = st.multiselect(
                "Status",
                options=sorted(df_alerts["Status"].unique()),
                default=["Active"],
                key="sec_status",
            )
        with sf3:
            srg_filter = st.multiselect(
                "Resource Group",
                options=sorted(df_alerts["ResourceGroup"].unique()),
                default=[],
                key="sec_rg",
            )

        sec_filtered = df_alerts.copy()
        if sev_filter:
            sec_filtered = sec_filtered[sec_filtered["Severity"].isin(sev_filter)]
        if status_filter:
            sec_filtered = sec_filtered[sec_filtered["Status"].isin(status_filter)]
        if srg_filter:
            sec_filtered = sec_filtered[sec_filtered["ResourceGroup"].isin(srg_filter)]

        # ── Severity distribution ─────────────────────────────────────────────
        st.markdown(
            severity_distribution_html(high_alerts, med_alerts, low_alerts),
            unsafe_allow_html=True,
        )

        # ── Alert cards ───────────────────────────────────────────────────────
        st.markdown('<div class="section-header">Security Alerts</div>', unsafe_allow_html=True)

        sec_sorted = sec_filtered.sort_values(
            "Severity",
            key=lambda s: s.map({"High": 0, "Medium": 1, "Low": 2}),
        )

        for _, row in sec_sorted.iterrows():
            sev = row["Severity"]
            color = ADVISOR_SEVERITY_COLORS.get(sev, "#ccc")
            status_icon = "🔴" if row["Status"] == "Active" else "✅"
            with st.expander(
                f"{severity_badge(sev)} [{sev}] {row['AlertType']}  —  "
                f"{row['ResourceGroup']} / {row['ResourceName']}  {status_icon}",
                expanded=(sev == "High"),
            ):
                a1, a2, a3 = st.columns(3)
                a1.markdown(f"**Severity:** <span style='color:{color};font-weight:700'>{sev}</span>",
                            unsafe_allow_html=True)
                a2.markdown(f"**Status:** {row['Status']}")
                a3.markdown(f"**Detected:** {row['DetectedAt']}")

                st.markdown(f"**Description:** {row['Description']}")
                if row.get("Remediation"):
                    st.markdown(
                        f"""
                        <div style="background:#e8f4fd;border-left:4px solid #0078d4;
                             padding:10px 14px;border-radius:4px;margin-top:8px;">
                            <b>🛠️ Remediation:</b> {row['Remediation']}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                st.caption(f"Resource: {row['ResourceName']}  |  Alert ID: {row['AlertId']}")

        # ── Export ────────────────────────────────────────────────────────────
        csv_sec = sec_filtered.to_csv(index=False).encode()
        st.download_button(
            "⬇️ Export Alerts to CSV",
            csv_sec,
            file_name=f"security_alerts_{datetime.utcnow().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )
    else:
        st.success("✅ No security alerts found for the selected resource groups.")

    # ── Security best-practice checklist ─────────────────────────────────────
    with st.expander("📋 Security Best-Practice Checklist", expanded=False):
        checks = [
            ("Defender for Cloud enabled on all subscriptions", True),
            ("Private Endpoints used for all PaaS services", True),
            ("NSG flow logs enabled and sent to Log Analytics", False),
            ("Storage accounts accessible only via private endpoint", True),
            ("Key Vault purge protection and soft-delete enabled", True),
            ("All VMs enrolled in Defender for Servers", False),
            ("JIT VM access configured", False),
            ("Azure Policy — DENY public IP assignment", True),
            ("RBAC — no standing Owner assignments for humans", True),
            ("Diagnostic settings on all resources", False),
        ]
        for label, done in checks:
            icon = "✅" if done else "❌"
            st.markdown(f"{icon} {label}")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — AI ASSISTANT (Azure OpenAI via Managed Identity)
# ═══════════════════════════════════════════════════════════════════════════════

with tab_chat:
    # Build context from data already loaded by the Cost & Advisor tabs.
    # Reload security alerts and secure_score so the assistant has full picture.
    df_alerts_for_chat = adv_mgr.security_alerts(selected_rgs)
    secure_score_for_chat = adv_mgr.secure_score()

    context_str = build_context(
        selected_rgs=selected_rgs,
        selected_rg=selected_rg,
        df_rg_summary=df_rg_summary,
        df_service=df_service,
        df_tx=df_tx,
        df_recs=df_recs,
        df_alerts=df_alerts_for_chat,
        secure_score=secure_score_for_chat,
    )

    render_chat_ui(context_str)
    render_clear_button()

    with st.expander("ℹ️ What context does the assistant see?", expanded=False):
        st.caption(
            "The assistant is grounded on the JSON snapshot below — it does NOT "
            "have arbitrary access to your subscription. Refresh the dashboard to "
            "give it fresh data."
        )
        st.code(context_str, language="json")
