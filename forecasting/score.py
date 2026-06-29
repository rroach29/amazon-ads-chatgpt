
def clamp(value, minimum=0, maximum=100):
    try:
        value = float(value)
    except Exception:
        value = 0
    return max(minimum, min(maximum, value))


def score_acos(acos):
    """Score ACOS where lower is better. Accepts decimal or percent-like values."""
    if acos is None:
        return 50
    acos = float(acos)
    if acos > 1:
        acos = acos / 100

    if acos <= 0.15:
        return 100
    if acos <= 0.20:
        return 90
    if acos <= 0.25:
        return 80
    if acos <= 0.30:
        return 70
    if acos <= 0.40:
        return 55
    if acos <= 0.60:
        return 35
    return 15


def score_roas(roas):
    if roas is None:
        return 50
    roas = float(roas)
    if roas >= 6:
        return 100
    if roas >= 5:
        return 90
    if roas >= 4:
        return 80
    if roas >= 3:
        return 70
    if roas >= 2:
        return 50
    if roas >= 1:
        return 30
    return 10


def score_decision_backlog(open_decisions):
    open_decisions = int(open_decisions or 0)
    if open_decisions <= 5:
        return 100
    if open_decisions <= 10:
        return 85
    if open_decisions <= 20:
        return 70
    if open_decisions <= 40:
        return 50
    return 30


def score_learning_accuracy(accuracy):
    if accuracy is None:
        return 60
    return clamp(accuracy)


def score_waste(estimated_waste, sales):
    estimated_waste = float(estimated_waste or 0)
    sales = float(sales or 0)

    if estimated_waste <= 0:
        return 100
    if sales <= 0:
        return 50

    waste_ratio = estimated_waste / sales

    if waste_ratio <= 0.02:
        return 95
    if waste_ratio <= 0.05:
        return 85
    if waste_ratio <= 0.10:
        return 70
    if waste_ratio <= 0.20:
        return 50
    return 30


def calculate_business_score(
    acos=None,
    roas=None,
    open_decisions=0,
    learning_accuracy=None,
    estimated_waste=0,
    sales=0,
):
    components = {
        "acos_score": score_acos(acos),
        "roas_score": score_roas(roas),
        "decision_backlog_score": score_decision_backlog(open_decisions),
        "learning_accuracy_score": score_learning_accuracy(learning_accuracy),
        "waste_score": score_waste(estimated_waste, sales),
    }

    weights = {
        "acos_score": 0.25,
        "roas_score": 0.20,
        "decision_backlog_score": 0.15,
        "learning_accuracy_score": 0.20,
        "waste_score": 0.20,
    }

    score = sum(components[key] * weights[key] for key in weights)

    if score >= 90:
        health = "EXCELLENT"
    elif score >= 80:
        health = "GOOD"
    elif score >= 65:
        health = "FAIR"
    elif score >= 50:
        health = "NEEDS_ATTENTION"
    else:
        health = "AT_RISK"

    return {
        "score": round(score, 1),
        "health": health,
        "components": components,
        "weights": weights,
    }
