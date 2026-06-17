import secrets
import csv

from django.contrib.auth.decorators import login_required
from django.db.models import Avg
from django.http import HttpResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.utils import timezone


from patient.models import Test, Trial, Response, Keystroke
from patient.export_utils import (
    DOCTOR_OVERVIEW_AGE_BRACKETS,
    classify_performance_band,
    format_boolean,
    format_datetime_for_csv,
    format_decimal,
    get_test_summary,
    get_trial_average_keystroke_latency,
)

#Fixed Trial Data for each test
FIXED_TRIALS = [
    # 6 digit-only
    {"trial_type": "DIGIT", "span_length": 4, "displayed_sequence": "3178"},
    {"trial_type": "DIGIT", "span_length": 4, "displayed_sequence": "5296"},
    {"trial_type": "DIGIT", "span_length": 4, "displayed_sequence": "4601"},
    {"trial_type": "DIGIT", "span_length": 5, "displayed_sequence": "29408"},
    {"trial_type": "DIGIT", "span_length": 5, "displayed_sequence": "13720"},
    {"trial_type": "DIGIT", "span_length": 5, "displayed_sequence": "60482"},

    # 6 alphanumerical
    {"trial_type": "ALPHANUMERIC", "span_length": 4, "displayed_sequence": "FR76"},
    {"trial_type": "ALPHANUMERIC", "span_length": 4, "displayed_sequence": "C59H"},
    {"trial_type": "ALPHANUMERIC", "span_length": 4, "displayed_sequence": "Q1M4"},
    {"trial_type": "ALPHANUMERIC", "span_length": 5, "displayed_sequence": "LA8Y5"},
    {"trial_type": "ALPHANUMERIC", "span_length": 5, "displayed_sequence": "901AW"},
    {"trial_type": "ALPHANUMERIC", "span_length": 5, "displayed_sequence": "2RH7M"},
]

# create trials for test
def generate_trials_for_test(test):
    trials = []

    for index, stimulus in enumerate(FIXED_TRIALS, start=1):
        trials.append(
            Trial(
                test=test,
                trial_type=stimulus["trial_type"],
                trial_number=index,
                span_length=stimulus["span_length"],
                displayed_sequence=stimulus["displayed_sequence"],
            )
        )

    Trial.objects.bulk_create(trials)



@login_required(login_url='login')
def patient_overview(request, test_id=None):
    all_tests = list(
        Test.objects.filter(
            doctor__user=request.user,
            status='COMPLETE',
        ).prefetch_related('trials__response__keystrokes').order_by('-completed_at', '-id')
    )

    selected_test_id = request.GET.get('test_id', '').strip()
    selected_test = None
    if test_id is not None:
        selected_test = get_object_or_404(
            Test.objects.filter(doctor__user=request.user).prefetch_related('trials__response__keystrokes'),
            id=test_id,
        )
        selected_test_id = str(selected_test.id)
    elif selected_test_id:
        try:
            selected_test = next(test for test in all_tests if test.id == int(selected_test_id))
        except (StopIteration, ValueError):
            selected_test = None
            selected_test_id = ''

    performance_data = []
    performance_bands = {
        'Excellent': 0,
        'Expected': 0,
        'Monitor': 0,
        'Follow up': 0,
        'No responses': 0,
    }

    for min_age, max_age, label in DOCTOR_OVERVIEW_AGE_BRACKETS:
        tests_in_bracket = [
            test for test in all_tests
            if min_age <= test.patient_age <= max_age
        ]
        summaries = [get_test_summary(test) for test in tests_in_bracket]
        mean_accuracies = [
            summary['mean_accuracy']
            for summary in summaries
            if summary['mean_accuracy'] is not None
        ]
        exact_match_rates = [
            summary['exact_match_rate']
            for summary in summaries
            if summary['exact_match_rate'] is not None
        ]

        selected_test_accuracy = None
        if selected_test is not None and min_age <= selected_test.patient_age <= max_age:
            selected_test_accuracy = get_test_summary(selected_test)['mean_accuracy']

        performance_data.append({
            'label': label,
            'reference_mean': round(sum(mean_accuracies) / len(mean_accuracies), 1) if mean_accuracies else 0,
            'observed_accuracy': round(sum(exact_match_rates) / len(exact_match_rates), 1) if exact_match_rates else 0,
            'selected_test_accuracy': round(selected_test_accuracy, 1) if selected_test_accuracy is not None else None,
            'test_count': len(tests_in_bracket),
        })

        for summary in summaries:
            performance_bands[classify_performance_band(summary['mean_accuracy'])] += 1

    completed_tests_for_select = []
    for min_age, max_age, label in DOCTOR_OVERVIEW_AGE_BRACKETS:
        grouped_tests = []
        for complete_test in all_tests:
            if min_age <= complete_test.patient_age <= max_age:
                summary = get_test_summary(complete_test)
                grouped_tests.append({
                    'id': complete_test.id,
                    'patient_age': complete_test.patient_age,
                    'mean_accuracy': format_decimal(summary['mean_accuracy'], 1) or '0.0',
                })
        if grouped_tests:
            completed_tests_for_select.append({
                'label': label,
                'tests': grouped_tests,
            })

    return render(request, 'doctor/patient_overview.html', {
        'performance_data': performance_data,
        'performance_bands': performance_bands,
        'completed_tests_for_select': completed_tests_for_select,
        'selected_test_id': selected_test_id,
    })


@login_required(login_url='login')
def export_patient_overview_csv(request):
    all_tests = list(
        Test.objects.filter(
            doctor__user=request.user,
            status='COMPLETE',
        ).prefetch_related('trials__response__keystrokes').order_by('id')
    )

    selected_test_id_raw = request.GET.get('test_id', '').strip()
    selected_test = None
    if selected_test_id_raw:
        try:
            selected_test = next(test for test in all_tests if test.id == int(selected_test_id_raw))
        except (StopIteration, TypeError, ValueError):
            selected_test = None

    tests_to_export = [selected_test] if selected_test is not None else list(all_tests)

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    filename_suffix = f"test_{selected_test.id}" if selected_test is not None else 'all_tests'
    response['Content-Disposition'] = f'attachment; filename="patient_overview_{filename_suffix}.csv"'
    response.write('\ufeff')

    writer = csv.writer(response)
    if selected_test is not None:
        summary = get_test_summary(selected_test)
        writer.writerow(['Report Type', 'Individual PPST Test Export'])
        writer.writerow(['Test ID', selected_test.id])
        writer.writerow(['Patient Age', selected_test.patient_age])
        writer.writerow(['Age Bracket', summary['age_bracket']])
        writer.writerow(['Test Status', selected_test.get_status_display()])
        writer.writerow(['Completed Trials', summary['completed_trials']])
        writer.writerow(['Total Trials', summary['total_trials']])
        writer.writerow(['Mean Accuracy (%)', format_decimal(summary['mean_accuracy'])])
        writer.writerow(['Exact Match Rate (%)', format_decimal(summary['exact_match_rate'])])
        writer.writerow(['Mean Response Latency (s)', format_decimal(summary['mean_response_latency'])])
        writer.writerow(['Mean Keystroke Latency (s)', format_decimal(summary['mean_keystroke_latency'])])
        writer.writerow(['Test Duration (s)', format_decimal(summary['duration_seconds'])])
        writer.writerow(['Test Started At', format_datetime_for_csv(selected_test.started_at)])
        writer.writerow(['Test Completed At', format_datetime_for_csv(selected_test.completed_at)])
        writer.writerow([])

        writer.writerow([
            'Trial #',
            'Sequence Category',
            'Span Length',
            'Displayed Sequence',
            'Patient Response',
            'Result',
            'Exact Match',
            'Correct Positions',
            'Accuracy (%)',
            'Response Latency (s)',
            'Avg Keystroke Latency (s)',
            'Total Keystrokes',
            'Extra Keystrokes',
        ])

        for trial in selected_test.trials.all().order_by('trial_number'):
            trial_response = getattr(trial, 'response', None)
            total_keystrokes = trial_response.keystrokes.count() if trial_response else 0
            average_keystroke_latency = get_trial_average_keystroke_latency(trial_response)

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
                format_decimal(trial_response.response_latency, 3) if trial_response else '',
                format_decimal(average_keystroke_latency, 3) if trial_response else '',
                total_keystrokes,
                max(total_keystrokes - len(trial.displayed_sequence), 0),
            ])
    else:
        writer.writerow(['Report Type', 'All PPST Tests Export'])
        writer.writerow([])

        writer.writerow([
            'Test ID',
            'Patient Age',
            'Age Bracket',
            'Test Status',
            'Completed Trials',
            'Total Trials',
            'Mean Accuracy (%)',
            'Exact Match Rate (%)',
            'Mean Response Latency (s)',
            'Mean Keystroke Latency (s)',
            'Test Duration (s)',
            'Test Started At',
            'Test Completed At',
        ])

        for test in tests_to_export:
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

        writer.writerow([])
        writer.writerow([
            'Test ID',
            'Trial #',
            'Sequence Category',
            'Span Length',
            'Displayed Sequence',
            'Patient Response',
            'Result',
            'Exact Match',
            'Correct Positions',
            'Accuracy (%)',
            'Response Latency (s)',
            'Avg Keystroke Latency (s)',
            'Total Keystrokes',
            'Extra Keystrokes',
        ])

        for test in tests_to_export:
            summary = get_test_summary(test)
            for trial in test.trials.all().order_by('trial_number'):
                trial_response = getattr(trial, 'response', None)
                total_keystrokes = trial_response.keystrokes.count() if trial_response else 0
                average_keystroke_latency = get_trial_average_keystroke_latency(trial_response)

                if trial_response is None:
                    result_label = 'No recorded response'
                elif trial_response.is_exact_match:
                    result_label = 'Exact match'
                else:
                    result_label = 'Partial / incorrect'

                writer.writerow([
                    test.id,
                    trial.trial_number,
                    trial.get_trial_type_display(),
                    trial.span_length,
                    trial.displayed_sequence,
                    trial_response.user_sequence if trial_response else '',
                    result_label,
                    format_boolean(trial_response.is_exact_match) if trial_response else '',
                    trial_response.correct_positions if trial_response else '',
                    format_decimal(trial_response.accuracy) if trial_response else '',
                    format_decimal(trial_response.response_latency, 3) if trial_response else '',
                    format_decimal(average_keystroke_latency, 3) if trial_response else '',
                    total_keystrokes,
                    max(total_keystrokes - len(trial.displayed_sequence), 0),
                ])

    return response


@login_required(login_url='login')
def dashboard(request):
    tests = Test.objects.filter(doctor__user=request.user).order_by('-created_at')
    search_type = (request.GET.get('search_type') or 'age').lower()
    search_value = (request.GET.get('search_value') or '').strip()
    
    if search_value:
        if search_type == 'age':
            try:
                patient_age = int(search_value)
                if patient_age > 0:
                    tests = tests.filter(patient_age=patient_age)
                else:
                    tests = tests.none()
            except ValueError:
                tests = tests.none()
        elif search_type == 'test_id':
            try:
                test_id = int(search_value)
                if test_id > 0:
                    tests = tests.filter(id=test_id)
                else:
                    tests = tests.none()
            except ValueError:
                tests = tests.none()

    completed_tests = []
    incomplete_tests = []
    did_not_complete_tests = []

    for test in tests:
        if (
            test.status == 'INCOMPLETE'
            and test.started_at is None
            and test.scheduled_for is not None
            and timezone.now() >= test.scheduled_for
        ):
            test.status = 'EXPIRED'
            test.completed_at = timezone.now()
            test.save(update_fields=['status', 'completed_at'])

        duration = None
        if test.started_at and test.completed_at:
            total_seconds = int((test.completed_at - test.started_at).total_seconds())
            minutes, seconds = divmod(max(total_seconds, 0), 60)
            duration = f"{minutes}m {seconds}s"

        row = {
            'id': test.id,
            'status': test.status,
            'display_status': test.get_status_display(),
            'created_at': test.created_at,
            'duration': duration,
        }

        if test.status == 'COMPLETE':
            completed_tests.append(row)
        elif test.status in ('ENDED_EARLY', 'EXPIRED'):
            did_not_complete_tests.append(row)
        else:
            row['patient_link'] = request.build_absolute_uri(
                reverse('patient:landing', args=[test.id])
            )
            incomplete_tests.append(row)

    return render(request, 'doctor/dashboard.html', {
        'completed_tests': completed_tests,
        'incomplete_tests': incomplete_tests,
        'search_type': search_type,
        'search_value': search_value,
        'did_not_complete_tests': did_not_complete_tests,
    })


@login_required(login_url='login')
def test_info(request):
    latest_test = Test.objects.filter(doctor__user=request.user).order_by('-created_at').first()
    if latest_test is None:
        return redirect('doctor:dashboard')
    return redirect('doctor:test_details', test_id=latest_test.id)


@login_required(login_url='login')
def create_test(request):
    if request.method != 'POST':
        return redirect('doctor:dashboard')
    
    patient_age_raw = request.POST.get('patient_age')
    #patient_age = int(request.POST.get('patient_age', '0') or 0)
    scheduled_for_raw = request.POST.get('scheduled_for')

    try:
        patient_age = int(patient_age_raw)
    except(TypeError,ValueError):
        return redirect('doctor:dashboard')
    if patient_age <= 0:
        return redirect('doctor:dashboard')
        
    scheduled_for = None
    if scheduled_for_raw:
        scheduled_for = parse_datetime(scheduled_for_raw)
        if scheduled_for is not None and timezone.is_naive(scheduled_for):
            scheduled_for = timezone.make_aware(
                scheduled_for,
                timezone.get_current_timezone(),
            )


    doctor = request.user.doctor
    test = Test.objects.create(
            doctor=doctor,
            patient_age=patient_age,
            scheduled_for = scheduled_for,
            access_token=secrets.token_hex(16),
        )
    
    generate_trials_for_test(test)

    return redirect('doctor:dashboard')

    ## For deleting tests
@login_required(login_url='login')
def delete_test(request, test_id):
    if request.method != 'POST':
        return redirect('doctor:dashboard')

    doctor = request.user.doctor
    test = get_object_or_404(Test, id=test_id, doctor=doctor)

    test.delete()

    return redirect('doctor:dashboard')

@login_required(login_url='login')
def test_details(request, test_id):
    doctor = request.user.doctor
    test = get_object_or_404(Test, id=test_id, doctor=doctor)
    doctor_tests = Test.objects.filter(doctor=doctor).order_by('-created_at')

    responses = Response.objects.filter(trial__test=test)
    total_responses = responses.count()
    exact_responses = responses.filter(is_exact_match=True).count()

    correct_response_percentage = None
    if total_responses > 0:
        correct_response_percentage = round((exact_responses / total_responses) * 100, 1)

    mean_latency = Keystroke.objects.filter(response__trial__test=test).aggregate(
        avg_latency=Avg('latency')
    )['avg_latency']

    time_taken = None
    if test.started_at and test.completed_at:
        total_seconds = int((test.completed_at - test.started_at).total_seconds())
        minutes, seconds = divmod(max(total_seconds, 0), 60)
        time_taken = f"{minutes}m {seconds}s"

    patient_link = request.build_absolute_uri(
        reverse('patient:landing', args=[test.id])
    )

    return render(request, 'doctor/test_details.html', {
        'test': test,
        'doctor_tests': doctor_tests,
        'patient_link': patient_link,
        'mean_latency': mean_latency,
        'correct_response_percentage': correct_response_percentage,
        'time_taken': time_taken,
    })
