import json
from django.http import JsonResponse
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Test, Response, Keystroke

import csv
from django.http import HttpResponse
from .export_utils import (
    AGE_GROUP_FILTERS,
    format_boolean,
    format_datetime_for_csv,
    format_decimal,
    get_test_summary,
    get_trial_average_keystroke_latency,
)


def mark_test_expired_if_due(test):
    if test.status != 'INCOMPLETE':
        return False

    if test.started_at is not None or test.scheduled_for is None:
        return False

    now = timezone.now()
    if now >= test.scheduled_for:
        test.status = 'EXPIRED'
        test.completed_at = now
        test.save(update_fields=['status', 'completed_at'])
        return True
    return False


def landing(request, test_id):
    test = get_object_or_404(Test, id=test_id)

    if mark_test_expired_if_due(test):
        return redirect('patient:complete', test_id=test.id)

    return render(request, 'patient/base_patient.html', {
        'test': test,
    })


def instructions(request, test_id):
    test = get_object_or_404(Test, id=test_id)

    if mark_test_expired_if_due(test):
        return redirect('patient:complete', test_id=test.id)

    return render(request, 'patient/instructions.html', {
        'test': test,
    })


def written_instructions(request, test_id):
    test = get_object_or_404(Test, id=test_id)

    if mark_test_expired_if_due(test):
        return redirect('patient:complete', test_id=test.id)

    return render(request, 'patient/written_instructions.html', {
        'test': test,
    })

# Compares patient's entered sequence to trial display sequence
# Returns:
    # is_exact_match
    # correct_positions
    # accuracy 
def score_user_sequence(displayed_sequence, user_sequence):

    correct_positions = 0
    for expected_char, actual_char in zip(displayed_sequence, user_sequence):
        if expected_char == actual_char:
            correct_positions += 1

    is_exact_match = displayed_sequence == user_sequence
    # denominator for taking into account extra keystrokes
    denominator = max(len(displayed_sequence), len(user_sequence), 1)
    accuracy = (correct_positions / denominator) * 100
    return {
        "is_exact_match": is_exact_match,
        "correct_positions": correct_positions,
        "accuracy": accuracy,
    }

# Helper function for fixed trial order
# returns newxt unsanswered trial 
def get_current_trial(test):
    return test.trials.filter(response__isnull=True).order_by('trial_number').first()


# Hardcoded practice questions
# 2 digit, 2 alphanumeric
PRACTICE_QUESTIONS = [
    {'displayed_sequence': '4729', 'trial_type': 'DIGIT'},
    {'displayed_sequence': '1583', 'trial_type': 'DIGIT'},
    {'displayed_sequence': 'A3H7', 'trial_type': 'ALPHANUMERIC'},
    {'displayed_sequence': 'R2W9', 'trial_type': 'ALPHANUMERIC'},
]

def practice_intro(request, test_id):
    test = get_object_or_404(Test, id=test_id)

    if mark_test_expired_if_due(test):
        return redirect('patient:complete', test_id=test.id)

    if test.started_at is not None:
        return redirect('patient:testing', test_id=test.id)

    return render(request, 'patient/practice_intro.html', {
        'test': test,
    })

def practice(request, test_id, question_num):
    test = get_object_or_404(Test, id=test_id)

    if mark_test_expired_if_due(test):
        return redirect('patient:complete', test_id=test.id)

    if test.started_at is not None:
        return redirect('patient:testing', test_id=test.id)

    if question_num < 1 or question_num > len(PRACTICE_QUESTIONS):
        return redirect('patient:practice_intro', test_id=test.id)

    if request.method == 'POST':
        # don't save anything, just advance
        if question_num < len(PRACTICE_QUESTIONS):
            return redirect('patient:practice', test_id=test.id, question_num=question_num + 1)
        else:
            return redirect('patient:practice_complete', test_id=test.id)

    trial = PRACTICE_QUESTIONS[question_num - 1]

    return render(request, 'patient/testing.html', {
        'test': test,
        'trial': trial,
        'trial_index': question_num,
        'total_trials': len(PRACTICE_QUESTIONS),
        'is_practice': True,
    })

def practice_complete(request, test_id):
    test = get_object_or_404(Test, id=test_id)

    if mark_test_expired_if_due(test):
        return redirect('patient:complete', test_id=test.id)

    if test.started_at is not None:
        return redirect('patient:testing', test_id=test.id)

    if request.method == 'POST':
        test.started_at = timezone.now()
        test.save(update_fields=['started_at'])
        return redirect('patient:testing', test_id=test.id)

    return render(request, 'patient/practice_complete.html', {
        'test': test,
    })


# ACTUAL TEST
def testing(request, test_id):
    test = get_object_or_404(Test, id=test_id)

    mark_test_expired_if_due(test)

    if test.status in ('ENDED_EARLY', 'EXPIRED'):
        return redirect('patient:complete', test_id=test.id)

    if test.started_at is None:
        return redirect('patient:practice_intro', test_id=test.id)

    current_trial = get_current_trial(test)

    # if all trials are done:
    if current_trial is None:
        if test.status != 'COMPLETE':
            test.status = 'COMPLETE'
            test.completed_at = timezone.now()
            test.save(update_fields = ['status', 'completed_at'])
        return redirect('patient:complete', test_id=test.id)

    if request.method == 'POST':

        user_sequence = request.POST.get('user_sequence', '')
        response_latency_raw = request.POST.get('response_latency', '')
        keystroke_log_raw = request.POST.get('keystroke_log', '[]')

        try:
            response_latency = float(response_latency_raw) if response_latency_raw != '' else None
        except (TypeError, ValueError):
            response_latency = None

        try:
            keystroke_log = json.loads(keystroke_log_raw)
            if not isinstance(keystroke_log, list):
                keystroke_log = []
        except json.JSONDecodeError:
            keystroke_log =[]


        scoring = score_user_sequence(
            displayed_sequence=current_trial.displayed_sequence,
            user_sequence=user_sequence,
        )

        with transaction.atomic():

            response = Response.objects.create(
            trial=current_trial,
            user_sequence=user_sequence,
            is_exact_match=scoring['is_exact_match'],
            correct_positions=scoring['correct_positions'],
            accuracy=scoring['accuracy'],
            response_latency=response_latency,
        )
            keystrokes_to_create = []

            for entry in keystroke_log:
                key_pressed = str(entry.get('key_pressed', '')).upper()[:1]
                position = entry.get('position')
                latency = entry.get('latency')

                if not key_pressed:
                    continue
                try:
                    position = int(position)
                except (TypeError, ValueError):
                    continue

                try:
                    latency = float(latency) if latency is not None else None
                except (TypeError, ValueError):
                    latency = None

                keystrokes_to_create.append(
                    Keystroke(
                        response=response,
                        key_pressed=key_pressed,
                        position=position,
                        latency=latency,
                    )
                )

            if keystrokes_to_create:
                Keystroke.objects.bulk_create(keystrokes_to_create)

        return redirect('patient:testing', test_id=test.id)
    
    total_trials = test.trials.count()
    completed_trials = test.trials.filter(response__isnull=False).count()

    return render(request, 'patient/testing.html', {
        'test': test,
        'trial': current_trial,
        'trial_index': completed_trials + 1,
        'total_trials': total_trials,
    })


def complete(request, test_id):
    test = get_object_or_404(Test, id=test_id)
    return render(request, 'patient/complete.html', {
        'test': test,
    })


@csrf_exempt
@require_POST
def abort_test(request, test_id):
    test = get_object_or_404(Test, id=test_id)

    if test.status == 'INCOMPLETE' and test.started_at is not None:
        has_unanswered_trial = test.trials.filter(response__isnull=True).exists()
        if has_unanswered_trial:
            test.status = 'ENDED_EARLY'
            test.completed_at = timezone.now()
            test.save(update_fields=['status', 'completed_at'])

    return JsonResponse({'ok': True, 'status': test.status})

@login_required(login_url='login')
def export_test_csv(request, test_id):
    test = get_object_or_404(
        Test.objects.prefetch_related('trials__response__keystrokes'),
        id=test_id,
        doctor__user=request.user,
    )
    summary = get_test_summary(test)

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="test_{test_id}.csv"'
    response.write('\ufeff')

    writer = csv.writer(response)
    writer.writerow(['Report Type', 'Individual PPST Test Export'])
    writer.writerow(['Test ID', test.id])
    writer.writerow(['Patient Age', test.patient_age])
    writer.writerow(['Age Bracket', summary['age_bracket']])
    writer.writerow(['Test Status', test.get_status_display()])
    writer.writerow(['Completed Trials', summary['completed_trials']])
    writer.writerow(['Total Trials', summary['total_trials']])
    writer.writerow(['Mean Accuracy (%)', format_decimal(summary['mean_accuracy'])])
    writer.writerow(['Exact Match Rate (%)', format_decimal(summary['exact_match_rate'])])
    writer.writerow(['Mean Response Latency (s)', format_decimal(summary['mean_response_latency'])])
    writer.writerow(['Mean Keystroke Latency (s)', format_decimal(summary['mean_keystroke_latency'])])
    writer.writerow(['Test Duration (s)', format_decimal(summary['duration_seconds'])])
    writer.writerow(['Test Started At', format_datetime_for_csv(test.started_at)])
    writer.writerow(['Test Completed At', format_datetime_for_csv(test.completed_at)])
    writer.writerow([])

    writer.writerow([
        "Trial #",
        "Sequence Category",
        "Span Length",
        "Displayed Sequence",
        "Patient Response",
        "Result",
        "Exact Match",
        "Correct Positions",
        "Accuracy (%)",
        "Response Latency (s)",
        "Avg Keystroke Latency (s)",
        "Total Keystrokes",
        "Extra Keystrokes",
    ])

    for trial in test.trials.all().order_by('trial_number'):
        trial_response = getattr(trial, 'response', None)
        total_keystrokes = trial_response.keystrokes.count() if trial_response else 0
        extra_keystrokes = max(total_keystrokes - len(trial.displayed_sequence), 0)

        if trial_response is None:
            result_label = 'No recorded response'
        elif trial_response.is_exact_match:
            result_label = 'Exact match'
        else:
            result_label = 'Partial / incorrect'

        writer.writerow([
            trial.trial_number,
            trial.get_trial_type_display(),
            trial.span_length,
            trial.displayed_sequence,
            trial_response.user_sequence if trial_response else '',
            result_label,
            format_boolean(trial_response.is_exact_match) if trial_response else '',
            trial_response.correct_positions if trial_response else '',
            format_decimal(trial_response.accuracy) if trial_response else '',
            format_decimal(trial_response.response_latency) if trial_response else '',
            format_decimal(get_trial_average_keystroke_latency(trial_response)) if trial_response else '',
            total_keystrokes,
            extra_keystrokes,
        ])

    return response

@login_required(login_url='login')
def export_all_tests_csv(request):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="all_tests_summary.csv"'
    response.write('\ufeff')

    writer = csv.writer(response)

    writer.writerow([
        "Test ID",
        "Patient Age",
        "Age Bracket",
        "Test Status",
        "Completed Trials",
        "Total Trials",
        "Mean Accuracy (%)",
        "Exact Match Rate (%)",
        "Mean Response Latency (s)",
        "Mean Keystroke Latency (s)",
        "Test Duration (s)",
        "Started At",
        "Completed At",
    ])

    tests = Test.objects.filter(
        doctor__user=request.user,
    ).prefetch_related('trials__response__keystrokes').order_by('id')

    for test in tests:
        summary = get_test_summary(test)

        writer.writerow([
            test.id,
            test.patient_age,
            summary['age_bracket'],
            test.get_status_display(),
            summary['completed_trials'],
            summary['total_trials'],
            format_decimal(summary['mean_accuracy']),
            format_decimal(summary['exact_match_rate']),
            format_decimal(summary['mean_response_latency']),
            format_decimal(summary['mean_keystroke_latency']),
            format_decimal(summary['duration_seconds']),
            format_datetime_for_csv(test.started_at),
            format_datetime_for_csv(test.completed_at),
        ])

    return response

@login_required(login_url='login')
def export_age_group_csv(request):
    age_bracket = request.GET.get('age_bracket', 'all')
    
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="age_group_summary.csv"'
    response.write('\ufeff')

    writer = csv.writer(response)

    writer.writerow([
        "Test ID",
        "Patient Age",
        "Age Bracket",
        "Test Status",
        "Completed Trials",
        "Total Trials",
        "Mean Accuracy (%)",
        "Exact Match Rate (%)",
        "Mean Response Latency (s)",
        "Mean Keystroke Latency (s)",
        "Test Duration (s)",
        "Started At",
        "Completed At",
    ])

    tests = Test.objects.filter(
        doctor__user=request.user,
    ).prefetch_related('trials__response__keystrokes').order_by('id')

    age_range = AGE_GROUP_FILTERS.get(age_bracket)
    if age_bracket != 'all' and age_range is not None:
        min_age, max_age = age_range
        tests = tests.filter(patient_age__gte=min_age, patient_age__lte=max_age)

    for test in tests:
        summary = get_test_summary(test)

        writer.writerow([
            test.id,
            test.patient_age,
            summary['age_bracket'],
            test.get_status_display(),
            summary['completed_trials'],
            summary['total_trials'],
            format_decimal(summary['mean_accuracy']),
            format_decimal(summary['exact_match_rate']),
            format_decimal(summary['mean_response_latency']),
            format_decimal(summary['mean_keystroke_latency']),
            format_decimal(summary['duration_seconds']),
            format_datetime_for_csv(test.started_at),
            format_datetime_for_csv(test.completed_at),
        ])

    return response
