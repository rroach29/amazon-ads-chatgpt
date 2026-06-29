from trends import build_trend_summary


def metric_direction(trends, metric):
    return (
        trends
        .get("account_trends", {})
        .get("metrics", {})
        .get(metric, {})
    )


def build_root_cause_analysis(metric: str = "acos", days: int = 14):
    trends = build_trend_summary(days=days)

    target = metric_direction(trends, metric)
    spend = metric_direction(trends, "spend")
    sales = metric_direction(trends, "sales")
    orders = metric_direction(trends, "orders")
    clicks = metric_direction(trends, "clicks")
    roas = metric_direction(trends, "roas")

    findings = []

    if not target:
        return {
            "status": "NO_DATA",
            "message": f"No trend data available for {metric}.",
        }

    if metric == "acos":
        if target.get("direction") == "UP":
            if spend.get("direction") == "UP":
                findings.append("Spend increased during the period.")
            if sales.get("direction") in ["DOWN", "FLAT"]:
                findings.append("Sales did not grow enough to offset the spend increase.")
            if orders.get("direction") in ["DOWN", "FLAT"]:
                findings.append("Orders were flat or down, which likely hurt efficiency.")
        elif target.get("direction") == "DOWN":
            findings.append("ACOS improved because advertising efficiency improved.")
            if sales.get("direction") == "UP":
                findings.append("Sales increased during the period.")
            if spend.get("direction") in ["DOWN", "FLAT"]:
                findings.append("Spend was controlled while sales improved.")

    elif metric == "sales":
        if target.get("direction") == "DOWN":
            if clicks.get("direction") == "DOWN":
                findings.append("Clicks declined, which likely reduced sales volume.")
            if orders.get("direction") == "DOWN":
                findings.append("Orders declined during the period.")
            if spend.get("direction") == "DOWN":
                findings.append("Spend also declined, which may have reduced traffic.")
        elif target.get("direction") == "UP":
            findings.append("Sales increased during the period.")
            if clicks.get("direction") == "UP":
                findings.append("Traffic increased, which likely contributed to sales growth.")
            if orders.get("direction") == "UP":
                findings.append("Orders increased, confirming stronger conversion activity.")

    elif metric == "roas":
        if target.get("direction") == "UP":
            findings.append("ROAS improved during the period.")
            if sales.get("direction") == "UP":
                findings.append("Sales increased.")
            if spend.get("direction") in ["DOWN", "FLAT"]:
                findings.append("Spend remained controlled.")
        elif target.get("direction") == "DOWN":
            findings.append("ROAS declined during the period.")
            if spend.get("direction") == "UP":
                findings.append("Spend increased.")
            if sales.get("direction") in ["DOWN", "FLAT"]:
                findings.append("Sales did not keep pace with spend.")

    if not findings:
        findings.append("The metric changed, but no clear primary driver was detected yet.")

    return {
        "status": "OK",
        "metric": metric,
        "days": days,
        "metric_trend": target,
        "supporting_trends": {
            "spend": spend,
            "sales": sales,
            "orders": orders,
            "clicks": clicks,
            "roas": roas,
        },
        "findings": findings,
    }
