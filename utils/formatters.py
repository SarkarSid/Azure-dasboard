from datetime import datetime, timedelta


def fmt_currency(amount: float, currency: str = "USD") -> str:
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.2f}M"
    if amount >= 1_000:
        return f"${amount / 1_000:.2f}K"
    return f"${amount:.2f}"


def fmt_delta(current: float, previous: float) -> tuple[str, str]:
    """Return (formatted delta string, color indicator)."""
    if previous == 0:
        return "N/A", "gray"
    delta_pct = ((current - previous) / previous) * 100
    sign = "+" if delta_pct >= 0 else ""
    color = "red" if delta_pct > 5 else ("green" if delta_pct < -5 else "gray")
    return f"{sign}{delta_pct:.1f}%", color


def fmt_bytes(size_bytes: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} EB"


def date_range(days: int) -> tuple[str, str]:
    end = datetime.utcnow()
    start = end - timedelta(days=days)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def severity_badge(severity: str) -> str:
    colors = {"High": "🔴", "Medium": "🟡", "Low": "🟢", "Informational": "🔵"}
    return colors.get(severity, "⚪")


def category_badge(category: str) -> str:
    badges = {
        "Cost": "💰",
        "Security": "🔐",
        "Reliability": "🏗️",
        "Performance": "⚡",
        "OperationalExcellence": "⚙️",
    }
    return badges.get(category, "📌")
