import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class AzureConfig:
    """
    Auth: Managed Identity in Azure Web App, `az login` locally.
    DefaultAzureCredential handles both — no client_id/client_secret needed.
    """
    subscription_id: str = field(default_factory=lambda: os.getenv("AZURE_SUBSCRIPTION_ID", ""))
    tenant_id: str = field(default_factory=lambda: os.getenv("AZURE_TENANT_ID", ""))
    resource_groups_filter: list = field(default_factory=lambda: [
        rg.strip()
        for rg in os.getenv("AZURE_RESOURCE_GROUPS", "").split(",")
        if rg.strip()
    ])

    # Azure OpenAI — uses Managed Identity (Cognitive Services OpenAI User RBAC)
    aoai_endpoint: str = field(default_factory=lambda: os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/"))
    aoai_deployment: str = field(default_factory=lambda: os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"))
    aoai_api_version: str = field(default_factory=lambda: os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview"))

    @property
    def is_configured(self) -> bool:
        return bool(self.subscription_id)

    @property
    def aoai_enabled(self) -> bool:
        return bool(self.aoai_endpoint)

    @property
    def subscription_scope(self) -> str:
        return f"/subscriptions/{self.subscription_id}"

    def resource_group_scope(self, rg_name: str) -> str:
        return f"/subscriptions/{self.subscription_id}/resourceGroups/{rg_name}"


@dataclass
class AppConfig:
    demo_mode: bool = field(default_factory=lambda: os.getenv("DEMO_MODE", "false").lower() == "true")
    default_lookback_days: int = field(default_factory=lambda: int(os.getenv("DEFAULT_LOOKBACK_DAYS", "30")))
    cost_alert_threshold_pct: int = field(default_factory=lambda: int(os.getenv("COST_ALERT_THRESHOLD_PERCENT", "80")))


AZURE_CFG = AzureConfig()
APP_CFG = AppConfig()


# Resource type display names
RESOURCE_TYPE_LABELS = {
    "microsoft.databricks/workspaces": "Azure Databricks",
    "microsoft.network/privateendpoints": "Private Endpoints",
    "microsoft.web/sites": "Azure Web Apps",
    "microsoft.web/serverfarms": "App Service Plans",
    "microsoft.network/virtualnetworks": "Virtual Networks",
    "microsoft.network/networksecuritygroups": "Network Security Groups",
    "microsoft.storage/storageaccounts": "Azure Storage",
    "microsoft.network/applicationgateways": "Application Gateway",
    "microsoft.keyvault/vaults": "Key Vault",
    "microsoft.sql/servers": "Azure SQL Server",
    "microsoft.sql/servers/databases": "Azure SQL Database",
    "microsoft.containerservice/managedclusters": "AKS",
    "microsoft.network/bastionhosts": "Azure Bastion",
    "microsoft.insights/components": "Application Insights",
    "microsoft.operationalinsights/workspaces": "Log Analytics",
}

SERVICE_ICONS = {
    "Azure Databricks": "⚡",
    "Private Endpoints": "🔒",
    "Azure Web Apps": "🌐",
    "App Service Plans": "📦",
    "Virtual Networks": "🕸️",
    "Azure Storage": "💾",
    "Application Gateway": "🔀",
    "Key Vault": "🗝️",
    "Azure SQL Database": "🗄️",
    "AKS": "☸️",
    "Network Security Groups": "🛡️",
    "Application Insights": "📊",
    "Log Analytics": "📋",
    "Azure Bastion": "🏰",
}

ADVISOR_CATEGORY_COLORS = {
    "Cost": "#f7c59f",
    "Security": "#e84855",
    "Reliability": "#3d85c8",
    "Performance": "#6aa84f",
    "OperationalExcellence": "#9900ff",
}

ADVISOR_SEVERITY_COLORS = {
    "High": "#e84855",
    "Medium": "#f7c59f",
    "Low": "#6aa84f",
}
