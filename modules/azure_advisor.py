from __future__ import annotations

import random
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from config import AZURE_CFG, APP_CFG


class AzureAdvisorManager:
    """Wraps Azure Advisor + Defender for Cloud APIs."""

    def __init__(self):
        self._advisor = None
        self._security = None
        if AZURE_CFG.is_configured and not APP_CFG.demo_mode:
            self._init_clients()

    def _init_clients(self):
        try:
            from azure.identity import DefaultAzureCredential
            from azure.mgmt.advisor import AdvisorManagementClient
            from azure.mgmt.security import SecurityCenter

            cred = DefaultAzureCredential()
            self._advisor = AdvisorManagementClient(cred, AZURE_CFG.subscription_id)
            self._security = SecurityCenter(cred, AZURE_CFG.subscription_id, "eastus")
        except Exception as exc:
            st.warning(f"Advisor/Security client init failed — demo mode. ({exc})")

    @property
    def live(self) -> bool:
        return self._advisor is not None

    # ─── Advisor Recommendations ──────────────────────────────────────────────

    @st.cache_data(ttl=600, show_spinner=False)
    def recommendations(_self, resource_groups: list[str] | None = None) -> pd.DataFrame:
        if not _self.live:
            return _demo_recommendations()

        rows = []
        for rec in _self._advisor.recommendations.list():
            rg = (rec.resource_metadata.resource_id or "").split("/")[4] if rec.resource_metadata else ""
            if resource_groups and rg.lower() not in [r.lower() for r in resource_groups]:
                continue
            rows.append({
                "Id": rec.name,
                "Category": rec.category,
                "Impact": rec.impact,
                "ResourceGroup": rg,
                "ResourceType": rec.resource_metadata.resource_type if rec.resource_metadata else "",
                "ResourceName": rec.resource_metadata.resource_name if rec.resource_metadata else "",
                "ShortDescription": rec.short_description.problem if rec.short_description else "",
                "Solution": rec.short_description.solution if rec.short_description else "",
                "PotentialSavings": _extract_savings(rec),
                "LastUpdated": rec.last_updated.strftime("%Y-%m-%d") if rec.last_updated else "",
            })
        df = pd.DataFrame(rows)
        if df.empty:
            return _demo_recommendations()
        return df

    # ─── Security Alerts ──────────────────────────────────────────────────────

    @st.cache_data(ttl=300, show_spinner=False)
    def security_alerts(_self, resource_groups: list[str] | None = None) -> pd.DataFrame:
        if not _self.live:
            return _demo_security_alerts()

        rows = []
        try:
            for alert in _self._security.alerts.list():
                rg = (alert.id or "").split("/")[4] if alert.id else ""
                if resource_groups and rg.lower() not in [r.lower() for r in resource_groups]:
                    continue
                rows.append({
                    "AlertId": alert.name,
                    "AlertType": alert.alert_type,
                    "Severity": alert.severity,
                    "Status": alert.status,
                    "ResourceGroup": rg,
                    "ResourceName": alert.compromised_entity or "",
                    "Description": alert.description or "",
                    "Remediation": alert.remediation_steps[0] if alert.remediation_steps else "",
                    "DetectedAt": alert.time_generated_utc.strftime("%Y-%m-%d %H:%M") if alert.time_generated_utc else "",
                })
        except Exception:
            return _demo_security_alerts()

        df = pd.DataFrame(rows)
        if df.empty:
            return _demo_security_alerts()
        return df

    # ─── Secure Score ────────────────────────────────────────────────────────

    @st.cache_data(ttl=600, show_spinner=False)
    def secure_score(_self) -> float:
        if not _self.live:
            return round(random.uniform(52, 78), 1)
        try:
            scores = list(_self._security.secure_scores.list())
            if scores:
                current = scores[0].score.current if scores[0].score else 0
                maximum = scores[0].score.max if scores[0].score else 100
                return round((current / maximum) * 100, 1) if maximum else 0.0
        except Exception:
            pass
        return 0.0


# ─── Savings extraction helper ────────────────────────────────────────────────

def _extract_savings(rec) -> float:
    try:
        ep = rec.extended_properties or {}
        val = ep.get("annualSavingsAmount") or ep.get("savingsAmount") or 0
        return float(val)
    except Exception:
        return 0.0


# ─── Demo data helpers ────────────────────────────────────────────────────────

_DEMO_REC_TEMPLATES = [
    # (Category, Impact, Problem, Solution, savings_range)
    ("Cost", "High",
     "Shutdown or resize underutilized Azure Databricks clusters",
     "Resize or shut down clusters that have been idle for more than 7 days to reduce compute costs.",
     (800, 2400)),
    ("Cost", "High",
     "Right-size or shutdown underutilized virtual machines",
     "Consider resizing or shutting down VMs with average CPU utilization below 5%.",
     (300, 900)),
    ("Cost", "Medium",
     "Delete unattached managed disks",
     "Unattached disks are incurring charges. Delete them or attach them to a VM.",
     (50, 250)),
    ("Cost", "Medium",
     "Reserve capacity for consistent Azure Storage usage",
     "Purchase reserved capacity for storage accounts with predictable usage patterns.",
     (120, 480)),
    ("Cost", "Low",
     "Use Azure Blob storage lifecycle management",
     "Transition blobs to cooler storage tiers automatically based on last-modified date.",
     (30, 120)),
    ("Security", "High",
     "Enable Microsoft Defender for Databases",
     "Enable Defender for your Azure SQL databases to detect anomalous activities.",
     (0, 0)),
    ("Security", "High",
     "Restrict SSH / RDP access from the internet",
     "Update NSG rules to deny inbound SSH/RDP from 0.0.0.0/0.",
     (0, 0)),
    ("Security", "Medium",
     "Enable Azure Key Vault soft-delete and purge protection",
     "Enable soft-delete and purge protection to prevent accidental or malicious deletion of secrets.",
     (0, 0)),
    ("Security", "Medium",
     "Rotate storage account access keys",
     "Access keys older than 90 days should be rotated to reduce exposure risk.",
     (0, 0)),
    ("Security", "Low",
     "Enable diagnostic logs for Web Apps",
     "Application and server logs should be sent to a Log Analytics workspace.",
     (0, 0)),
    ("Reliability", "High",
     "Configure geo-redundant storage for critical data",
     "Switch to GRS or GZRS to protect against regional outages.",
     (0, 0)),
    ("Reliability", "Medium",
     "Enable Azure Site Recovery for production VMs",
     "Configure replication to a secondary region for business continuity.",
     (0, 0)),
    ("Reliability", "Low",
     "Set up autoscale rules for App Service Plans",
     "Enable autoscale to handle unexpected traffic spikes without manual intervention.",
     (0, 0)),
    ("Performance", "Medium",
     "Use premium SSD for I/O-intensive workloads",
     "Migrate workloads with high IOPS requirements to Premium SSD managed disks.",
     (0, 0)),
    ("Performance", "Low",
     "Enable Azure CDN for static content delivery",
     "Serve static assets via CDN to reduce latency for global users.",
     (0, 0)),
    ("OperationalExcellence", "Medium",
     "Configure resource health alerts",
     "Set up Azure Monitor health alerts so your team is notified before users are impacted.",
     (0, 0)),
    ("OperationalExcellence", "Low",
     "Tag all resources for cost allocation",
     "Apply consistent tags (environment, owner, cost-center) to enable accurate reporting.",
     (0, 0)),
]

_DEMO_RESOURCE_GROUPS_ADV = [
    "rg-prod-platform",
    "rg-prod-data",
    "rg-prod-network",
    "rg-prod-security",
    "rg-staging",
]

_DEMO_RESOURCE_NAMES = [
    "databricks-prod-ws",
    "stg-prod-datalake",
    "app-platform-api",
    "vnet-prod-hub",
    "kv-prod-secrets",
    "sql-prod-primary",
    "agw-prod-ingress",
    "stg-staging-data",
]


def _demo_recommendations() -> pd.DataFrame:
    rng = random.Random(42)
    rows = []
    for i, (cat, impact, problem, solution, savings_range) in enumerate(_DEMO_REC_TEMPLATES):
        lo, hi = savings_range
        rows.append({
            "Id": f"demo-rec-{i:03d}",
            "Category": cat,
            "Impact": impact,
            "ResourceGroup": rng.choice(_DEMO_RESOURCE_GROUPS_ADV),
            "ResourceType": rng.choice(["microsoft.databricks/workspaces", "microsoft.storage/storageaccounts",
                                         "microsoft.web/sites", "microsoft.network/virtualnetworks",
                                         "microsoft.sql/servers/databases"]),
            "ResourceName": rng.choice(_DEMO_RESOURCE_NAMES),
            "ShortDescription": problem,
            "Solution": solution,
            "PotentialSavings": round(rng.uniform(lo, hi), 2) if hi > 0 else 0.0,
            "LastUpdated": (datetime.utcnow() - timedelta(days=rng.randint(0, 14))).strftime("%Y-%m-%d"),
        })
    return pd.DataFrame(rows)


_DEMO_ALERT_TEMPLATES = [
    ("High", "Active", "Possible Brute Force Attack", "An unusually large number of failed authentication attempts was detected.",
     "Block the source IP in your NSG and rotate credentials immediately."),
    ("High", "Active", "Traffic from suspicious IP", "Network traffic was detected from a known malicious IP address.",
     "Review NSG flow logs and block the IP range. Enable Defender for Network."),
    ("Medium", "Active", "SQL injection-like patterns detected", "Anomalous SQL queries were observed on the production database.",
     "Review recent query logs and enable Advanced Threat Protection."),
    ("Medium", "Resolved", "Storage account accessible from internet", "A storage account is publicly accessible without firewall restrictions.",
     "Enable storage firewall and restrict access to known VNets/IPs."),
    ("Medium", "Active", "Overly permissive Key Vault access policy", "A service principal has full access to Key Vault secrets.",
     "Apply least-privilege access policies. Use RBAC instead of vault access policies."),
    ("Low", "Active", "Missing endpoint protection on VM", "One or more VMs do not have endpoint protection (antimalware) enabled.",
     "Deploy Microsoft Antimalware extension via Azure Policy."),
    ("Low", "Resolved", "Security contact not configured", "No security contact email is configured for this subscription.",
     "Configure a security contact in Microsoft Defender for Cloud settings."),
    ("Low", "Active", "Diagnostic logs disabled for App Service",
     "Web application request/response logging is not enabled.",
     "Enable application logging and send to Log Analytics workspace."),
]


def _demo_security_alerts() -> pd.DataFrame:
    rng = random.Random(99)
    rows = []
    for i, (severity, status, alert_type, desc, remediation) in enumerate(_DEMO_ALERT_TEMPLATES):
        rows.append({
            "AlertId": f"demo-alert-{i:03d}",
            "AlertType": alert_type,
            "Severity": severity,
            "Status": status,
            "ResourceGroup": rng.choice(_DEMO_RESOURCE_GROUPS_ADV),
            "ResourceName": rng.choice(_DEMO_RESOURCE_NAMES),
            "Description": desc,
            "Remediation": remediation,
            "DetectedAt": (datetime.utcnow() - timedelta(hours=rng.randint(1, 72))).strftime("%Y-%m-%d %H:%M"),
        })
    return pd.DataFrame(rows)
