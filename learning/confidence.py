
def clamp(value, minimum=0, maximum=99):
    return max(minimum, min(maximum, value))


def calculate_accuracy_percent(estimated_impact, actual_impact):
    estimated = float(estimated_impact or 0)
    actual = float(actual_impact or 0)

    if estimated == 0 and actual == 0:
        return 100.0

    if estimated == 0:
        return 0.0

    error = abs(estimated - actual) / abs(estimated)
    accuracy = max(0, 100 - (error * 100))
    return round(accuracy, 2)


def adjusted_confidence(confidence_before, accuracy_percent):
    before = float(confidence_before or 0)
    accuracy = float(accuracy_percent or 0)

    # Conservative first-pass adjustment: move 20% of the way toward observed accuracy.
    after = (before * 0.8) + (accuracy * 0.2)
    return round(clamp(after), 2)
