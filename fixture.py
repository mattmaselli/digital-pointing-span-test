"""Simple local seed script for PPST demo data.

Usage:
  python manage.py shell -c "exec(open('fixtures.py').read())"
  python manage.py shell < fixtures.py
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.utils import timezone

from doctor.models import Doctor
from doctor.views import generate_trials_for_test
from patient.models import Keystroke, Response, Test


PROFILE_PATTERNS = {
    "excellent": [0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 1],
    "expected": [0, 0, 1, 1, 0, 2, 0, 1, 2, 1, 0, 2],
    "monitor": [0, 1, 2, 2, 1, 3, 0, 2, 3, 1, 2, 3],
    "follow_up": [1, 2, 3, 4, 2, 5, 1, 3, 4, 2, 4, 5],
}

DEMO_TESTS = [
    {"token": "demo-token-0001", "age": 22, "profile": "excellent", "days_ago": 20},
    {"token": "demo-token-0002", "age": 27, "profile": "expected", "days_ago": 19},
    {"token": "demo-token-0003", "age": 30, "profile": "monitor", "days_ago": 18},
    {"token": "demo-token-0004", "age": 33, "profile": "excellent", "days_ago": 17},
    {"token": "demo-token-0005", "age": 40, "profile": "expected", "days_ago": 16},
    {"token": "demo-token-0006", "age": 45, "profile": "follow_up", "days_ago": 15},
    {"token": "demo-token-0007", "age": 49, "profile": "excellent", "days_ago": 14},
    {"token": "demo-token-0008", "age": 55, "profile": "monitor", "days_ago": 13},
    {"token": "demo-token-0009", "age": 60, "profile": "expected", "days_ago": 12},
    {"token": "demo-token-0010", "age": 63, "profile": "excellent", "days_ago": 11},
    {"token": "demo-token-0011", "age": 70, "profile": "expected", "days_ago": 10},
    {"token": "demo-token-0012", "age": 75, "profile": "follow_up", "days_ago": 9},
    {"token": "demo-token-0013", "age": 79, "profile": "excellent", "days_ago": 8},
    {"token": "demo-token-0014", "age": 84, "profile": "monitor", "days_ago": 7},
    {"token": "demo-token-0015", "age": 91, "profile": "expected", "days_ago": 6},
]


def rotate_char(char):
    if char.isdigit():
        return str((int(char) + 5) % 10)
    if char.isalpha():
        offset = (ord(char.upper()) - ord("A") + 7) % 26
        return chr(ord("A") + offset)
    return "X"


def build_user_sequence(displayed_sequence, mistakes, add_extra_keystroke=False):
    user_chars = list(displayed_sequence)
    max_mistakes = min(mistakes, len(user_chars))

    for index in range(max_mistakes):
        user_chars[index] = rotate_char(user_chars[index])

    user_sequence = "".join(user_chars)
    if add_extra_keystroke:
        user_sequence += "9"
    return user_sequence


def build_response_payload(trial, mistakes, response_latency):
    add_extra_keystroke = mistakes > 0 and trial.trial_number % 4 == 0
    user_sequence = build_user_sequence(
        trial.displayed_sequence,
        mistakes=mistakes,
        add_extra_keystroke=add_extra_keystroke,
    )
    correct_positions = max(trial.span_length - min(mistakes, trial.span_length), 0)
    accuracy = round((correct_positions / trial.span_length) * 100, 1)

    response = Response.objects.create(
        trial=trial,
        user_sequence=user_sequence,
        is_exact_match=mistakes == 0,
        correct_positions=correct_positions,
        accuracy=accuracy,
        response_latency=response_latency,
    )

    for position, key in enumerate(user_sequence, start=1):
        Keystroke.objects.create(
            response=response,
            key_pressed=key,
            position=position,
            latency=round(0.32 + (position * 0.07) + (mistakes * 0.05), 2),
        )


def seed_completed_test(doctor, config):
    started_at = timezone.now() - timedelta(days=config["days_ago"], minutes=6)
    completed_at = started_at + timedelta(minutes=4, seconds=30)
    scheduled_for = started_at - timedelta(minutes=15)

    test, _ = Test.objects.get_or_create(
        doctor=doctor,
        access_token=config["token"],
        defaults={
            "patient_age": config["age"],
            "status": "COMPLETE",
            "scheduled_for": scheduled_for,
            "started_at": started_at,
            "completed_at": completed_at,
        },
    )

    test.patient_age = config["age"]
    test.status = "COMPLETE"
    test.scheduled_for = scheduled_for
    test.started_at = started_at
    test.completed_at = completed_at
    test.save(update_fields=["patient_age", "status", "scheduled_for", "started_at", "completed_at"])

    test.trials.all().delete()
    generate_trials_for_test(test)

    mistake_pattern = PROFILE_PATTERNS[config["profile"]]
    for index, trial in enumerate(test.trials.order_by("trial_number")):
        response_latency = round(1.05 + (index * 0.11) + (mistake_pattern[index] * 0.18), 2)
        build_response_payload(trial, mistakes=mistake_pattern[index], response_latency=response_latency)

    return test


user, _ = User.objects.get_or_create(username="demo_doctor")
user.set_password("demo1234!")
user.save(update_fields=["password"])

doctor, _ = Doctor.objects.get_or_create(user=user)

desired_tokens = [config["token"] for config in DEMO_TESTS]
doctor.tests.filter(access_token__startswith="demo-token-").exclude(access_token__in=desired_tokens).delete()

seeded_tests = [seed_completed_test(doctor, config) for config in DEMO_TESTS]

print(f"Seed complete: demo_doctor / demo1234! ({len(seeded_tests)} completed demo tests)")
