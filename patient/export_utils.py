from django.utils import timezone


CSV_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S %Z"
DOCTOR_OVERVIEW_AGE_BRACKETS = [
    (18, 30, "18-30"),
    (31, 45, "31-45"),
    (46, 60, "46-60"),
    (61, 75, "61-75"),
    (76, 200, "76+"),
]
AGE_GROUP_FILTERS = {
    "all": None,
    "0-17": (0, 17),
    "18-30": (18, 30),
    "31-45": (31, 45),
    "46-60": (46, 60),
    "61-75": (61, 75),
    "76+": (76, 200),
}


def format_datetime_for_csv(value):
    if value is None:
        return ""
    local_value = timezone.localtime(value) if timezone.is_aware(value) else value
    return local_value.strftime(CSV_DATETIME_FORMAT)


def format_decimal(value, digits=2):
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def format_boolean(value):
    return "Yes" if value else "No"


def get_age_bracket_label(age):
    if age is None:
        return ""
    if age < 18:
        return "0-17"
    for min_age, max_age, label in DOCTOR_OVERVIEW_AGE_BRACKETS:
        if min_age <= age <= max_age:
            return label
    return "76+"


def get_test_duration_seconds(test):
    if test.started_at and test.completed_at:
        return max((test.completed_at - test.started_at).total_seconds(), 0)
    return None


def get_test_duration_display(test):
    total_seconds = get_test_duration_seconds(test)
    if total_seconds is None:
        return ""
    whole_seconds = int(total_seconds)
    minutes, seconds = divmod(whole_seconds, 60)
    return f"{minutes}m {seconds}s"


def get_trial_average_keystroke_latency(response):
    if response is None:
        return None
    latencies = [
        keystroke.latency
        for keystroke in response.keystrokes.all()
        if keystroke.latency is not None
    ]
    if not latencies:
        return None
    return sum(latencies) / len(latencies)


def get_test_summary(test):
    trials = list(test.trials.all())
    responses = [
        trial.response
        for trial in trials
        if hasattr(trial, "response")
    ]
    completed_trials = len(responses)
    total_trials = len(trials)

    accuracies = [response.accuracy for response in responses if response.accuracy is not None]
    response_latencies = [
        response.response_latency
        for response in responses
        if response.response_latency is not None
    ]
    keystroke_latencies = [
        keystroke.latency
        for response in responses
        for keystroke in response.keystrokes.all()
        if keystroke.latency is not None
    ]
    exact_match_count = sum(1 for response in responses if response.is_exact_match)

    return {
        "age_bracket": get_age_bracket_label(test.patient_age),
        "completed_trials": completed_trials,
        "total_trials": total_trials,
        "mean_accuracy": (
            sum(accuracies) / len(accuracies)
            if accuracies else None
        ),
        "exact_match_rate": (
            (exact_match_count / completed_trials) * 100
            if completed_trials else None
        ),
        "mean_response_latency": (
            sum(response_latencies) / len(response_latencies)
            if response_latencies else None
        ),
        "mean_keystroke_latency": (
            sum(keystroke_latencies) / len(keystroke_latencies)
            if keystroke_latencies else None
        ),
        "duration_seconds": get_test_duration_seconds(test),
        "duration_display": get_test_duration_display(test),
    }


def classify_performance_band(mean_accuracy):
    if mean_accuracy is None:
        return "No responses"
    if mean_accuracy >= 85:
        return "Excellent"
    if mean_accuracy >= 70:
        return "Expected"
    if mean_accuracy >= 50:
        return "Monitor"
    return "Follow up"
