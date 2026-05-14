from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import streamlit as st

from config import AZURE_CFG, APP_CFG, RESOURCE_TYPE_LABELS


class AzureCostManager:
    """Wraps Azure Cost Management queries with a demo-mode fallback."""

    def __init__(self):
        self._client = None
        self._resource_client = None
        if AZURE_CFG.is_configured and not APP_CFG.demo_mode:
            self._init_clients()

    def _init_clients(self):
        try:
            from azure.identity import DefaultAzureCredential
            from azure.mgmt.costmanagement import CostManagementClient
            from azure.mgmt.resource import ResourceManagementClient

            cred = DefaultAzureCredential()
            self._client = CostManagementClient(cred)
            self._resource_client = ResourceManagementClient(cred, AZURE_CFG.subscription_id)
        except Exception as exc:
            st.warning(f"Azure credential init failed — running in demo mode. ({exc})")

    @property
    def live(self) -> bool:
        return self._client is not None

    # ─── Resource Groups ──────────────────────────────────────────────────────

    @st.cache_data(ttl=300, show_spinner=False)
    def list_resource_groups(_self) -> list[str]:
        if not _self.live:
            return _DEMO_RESOURCE_GROUPS

        rg_list = [rg.name for rg in _self._resource_client.resource_groups.list()]
        if AZURE_CFG.resource_groups_filter:
            rg_list = [r for r in rg_list if r in AZURE_CFG.resource_groups_filter]
        return sorted(rg_list)

    # ─── Cost by Resource Type ────────────────────────────────────────────────

    @st.cache_data(ttl=300, show_spinner=False)
    def cost_by_service(_self, resource_group: str, start: str, end: str) -> pd.DataFrame:
        """Returns a DataFrame with columns: ServiceName, ResourceType, Cost, Currency."""
        if not _self.live:
            return _demo_cost_by_service(resource_group)

        from azure.mgmt.costmanagement.models import (
            QueryDefinition, QueryTimePeriod, QueryDataset,
            QueryAggregation, QueryGrouping,
        )

        scope = AZURE_CFG.resource_group_scope(resource_group)
        params = QueryDefinition(
            type="Usage",
            timeframe="Custom",
            time_period=QueryTimePeriod(from_property=start, to=end),
            dataset=QueryDataset(
                granularity="None",
                aggregation={"totalCost": QueryAggregation(name="Cost", function="Sum")},
                grouping=[
                    QueryGrouping(type="Dimension", name="ServiceName"),
                    QueryGrouping(type="Dimension", name="ResourceType"),
                ],
            ),
        )
        result = _self._client.query.usage(scope, params)
        rows = []
        cols = [c.name for c in result.columns]
        for row in result.rows:
            r = dict(zip(cols, row))
            rt = r.get("ResourceType", "").lower()
            r["ServiceLabel"] = RESOURCE_TYPE_LABELS.get(rt, r.get("ServiceName", rt))
            rows.append(r)

        df = pd.DataFrame(rows)
        df = df.rename(columns={"Cost": "Cost", "ServiceName": "ServiceName"})
        df["Cost"] = pd.to_numeric(df["Cost"], errors="coerce").fillna(0)
        return df

    # ─── Daily cost trend ─────────────────────────────────────────────────────

    @st.cache_data(ttl=300, show_spinner=False)
    def daily_cost_trend(_self, resource_group: str, start: str, end: str) -> pd.DataFrame:
        """Returns columns: Date, ServiceName, Cost."""
        if not _self.live:
            return _demo_daily_trend(resource_group, start, end)

        from azure.mgmt.costmanagement.models import (
            QueryDefinition, QueryTimePeriod, QueryDataset,
            QueryAggregation, QueryGrouping,
        )

        scope = AZURE_CFG.resource_group_scope(resource_group)
        params = QueryDefinition(
            type="Usage",
            timeframe="Custom",
            time_period=QueryTimePeriod(from_property=start, to=end),
            dataset=QueryDataset(
                granularity="Daily",
                aggregation={"totalCost": QueryAggregation(name="Cost", function="Sum")},
                grouping=[QueryGrouping(type="Dimension", name="ServiceName")],
            ),
        )
        result = _self._client.query.usage(scope, params)
        cols = [c.name for c in result.columns]
        rows = [dict(zip(cols, row)) for row in result.rows]
        df = pd.DataFrame(rows)
        df["Date"] = pd.to_datetime(df["UsageDate"], format="%Y%m%d", errors="coerce")
        df["Cost"] = pd.to_numeric(df["Cost"], errors="coerce").fillna(0)
        return df[["Date", "ServiceName", "Cost"]]

    # ─── Data transmission costs ───────────────────────────────────────────────

    @st.cache_data(ttl=300, show_spinner=False)
    def data_transmission_costs(_self, resource_group: str, start: str, end: str) -> pd.DataFrame:
        """Returns columns: Date, EgressCost, IngressCost, InterRegionCost."""
        if not _self.live:
            return _demo_transmission(start, end)

        from azure.mgmt.costmanagement.models import (
            QueryDefinition, QueryTimePeriod, QueryDataset,
            QueryAggregation, QueryGrouping, QueryFilter,
            QueryComparisonExpression,
        )

        scope = AZURE_CFG.resource_group_scope(resource_group)
        params = QueryDefinition(
            type="Usage",
            timeframe="Custom",
            time_period=QueryTimePeriod(from_property=start, to=end),
            dataset=QueryDataset(
                granularity="Daily",
                aggregation={"totalCost": QueryAggregation(name="Cost", function="Sum")},
                grouping=[QueryGrouping(type="Dimension", name="MeterCategory")],
                filter=QueryFilter(
                    dimensions=QueryComparisonExpression(
                        name="MeterCategory",
                        operator="In",
                        values=["Bandwidth", "Azure Data Transfer"],
                    )
                ),
            ),
        )
        result = _self._client.query.usage(scope, params)
        cols = [c.name for c in result.columns]
        rows = [dict(zip(cols, row)) for row in result.rows]
        df = pd.DataFrame(rows)
        if df.empty:
            return _demo_transmission(start, end)

        df["Date"] = pd.to_datetime(df.get("UsageDate", ""), format="%Y%m%d", errors="coerce")
        df["Cost"] = pd.to_numeric(df["Cost"], errors="coerce").fillna(0)
        cat = df.groupby(["Date", "MeterCategory"])["Cost"].sum().unstack(fill_value=0).reset_index()

        out = pd.DataFrame({"Date": cat["Date"]})
        out["EgressCost"] = cat.get("Bandwidth", 0)
        out["IngressCost"] = cat.get("Azure Data Transfer", 0)
        out["InterRegionCost"] = 0.0
        return out

    # ─── All-RG summary ───────────────────────────────────────────────────────

    @st.cache_data(ttl=300, show_spinner=False)
    def all_rg_cost_summary(_self, resource_groups: list[str], start: str, end: str) -> pd.DataFrame:
        """Returns columns: ResourceGroup, Cost for a quick overview."""
        if not _self.live:
            return _demo_rg_summary(resource_groups)

        from azure.mgmt.costmanagement.models import (
            QueryDefinition, QueryTimePeriod, QueryDataset,
            QueryAggregation, QueryGrouping,
        )

        scope = AZURE_CFG.subscription_scope
        params = QueryDefinition(
            type="Usage",
            timeframe="Custom",
            time_period=QueryTimePeriod(from_property=start, to=end),
            dataset=QueryDataset(
                granularity="None",
                aggregation={"totalCost": QueryAggregation(name="Cost", function="Sum")},
                grouping=[QueryGrouping(type="Dimension", name="ResourceGroupName")],
            ),
        )
        result = _self._client.query.usage(scope, params)
        cols = [c.name for c in result.columns]
        rows = [dict(zip(cols, row)) for row in result.rows]
        df = pd.DataFrame(rows).rename(columns={"ResourceGroupName": "ResourceGroup"})
        df["Cost"] = pd.to_numeric(df["Cost"], errors="coerce").fillna(0)
        if resource_groups:
            df = df[df["ResourceGroup"].isin(resource_groups)]
        return df[["ResourceGroup", "Cost"]].sort_values("Cost", ascending=False)


# ─── Demo data helpers ────────────────────────────────────────────────────────

_DEMO_RESOURCE_GROUPS = [
    "rg-prod-platform",
    "rg-prod-data",
    "rg-prod-network",
    "rg-prod-security",
    "rg-staging",
]

_DEMO_SERVICES = {
    "rg-prod-data": {
        "Azure Databricks": (4200, 5800),
        "Azure Storage": (420, 680),
        "Log Analytics": (280, 420),
        "Application Insights": (90, 180),
        "Key Vault": (20, 50),
    },
    "rg-prod-platform": {
        "Azure Web Apps": (1100, 1600),
        "App Service Plans": (320, 560),
        "Application Gateway": (480, 720),
        "Azure SQL Database": (680, 980),
        "Application Insights": (140, 220),
    },
    "rg-prod-network": {
        "Virtual Networks": (80, 160),
        "Private Endpoints": (140, 280),
        "Network Security Groups": (20, 50),
        "Azure Bastion": (320, 480),
    },
    "rg-prod-security": {
        "Key Vault": (80, 140),
        "Azure Storage": (120, 200),
        "Log Analytics": (320, 480),
    },
    "rg-staging": {
        "Azure Web Apps": (280, 420),
        "Azure Databricks": (680, 1100),
        "Azure Storage": (80, 160),
    },
}


def _demo_cost_by_service(resource_group: str) -> pd.DataFrame:
    rng = random.Random(resource_group)
    services = _DEMO_SERVICES.get(resource_group, {"Azure Web Apps": (400, 800), "Azure Storage": (100, 300)})
    rows = []
    for svc, (lo, hi) in services.items():
        rows.append({
            "ServiceName": svc,
            "ServiceLabel": svc,
            "ResourceType": svc,
            "Cost": round(rng.uniform(lo, hi), 2),
            "Currency": "USD",
        })
    return pd.DataFrame(rows).sort_values("Cost", ascending=False)


def _demo_daily_trend(resource_group: str, start: str, end: str) -> pd.DataFrame:
    rng = random.Random(resource_group + start)
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    days = (end_dt - start_dt).days
    services = list(_DEMO_SERVICES.get(resource_group, {"Azure Web Apps": (400, 800)}).keys())
    rows = []
    for d in range(days):
        date = start_dt + timedelta(days=d)
        for svc in services:
            lo, hi = _DEMO_SERVICES.get(resource_group, {}).get(svc, (50, 200))
            daily_base = (lo + hi) / 2 / 30
            rows.append({
                "Date": date,
                "ServiceName": svc,
                "Cost": round(daily_base * rng.uniform(0.7, 1.4), 2),
            })
    return pd.DataFrame(rows)


def _demo_transmission(start: str, end: str) -> pd.DataFrame:
    rng = random.Random(start)
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    days = (end_dt - start_dt).days
    rows = []
    for d in range(days):
        date = start_dt + timedelta(days=d)
        rows.append({
            "Date": date,
            "EgressCost": round(rng.uniform(18, 65), 2),
            "IngressCost": round(rng.uniform(2, 12), 2),
            "InterRegionCost": round(rng.uniform(5, 28), 2),
        })
    return pd.DataFrame(rows)


def _demo_rg_summary(resource_groups: list[str]) -> pd.DataFrame:
    rows = []
    for rg in resource_groups:
        services = _DEMO_SERVICES.get(rg, {"Azure Web Apps": (400, 800)})
        rng = random.Random(rg)
        total = sum(rng.uniform(lo, hi) for lo, hi in services.values())
        rows.append({"ResourceGroup": rg, "Cost": round(total, 2)})
    return pd.DataFrame(rows).sort_values("Cost", ascending=False)
