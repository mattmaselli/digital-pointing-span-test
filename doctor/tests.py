import csv
from datetime import timedelta
from io import StringIO

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from doctor.models import Doctor
from doctor.views import generate_trials_for_test
from patient.models import Keystroke, Response, Test


class DashboardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='demo_doctor', password='demo1234!')
        self.doctor = Doctor.objects.create(user=self.user)

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('doctor:dashboard'))
        self.assertEqual(response.status_code, 302)

    def test_create_test_redirects_to_patient_link(self):
        self.client.login(username='demo_doctor', password='demo1234!')
        response = self.client.post(reverse('doctor:create_test'), {'patient_age': 66})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Test.objects.count(), 1)

    def test_patient_overview_page_builds_spreadsheet_context(self):
        self.client.login(username='demo_doctor', password='demo1234!')
        complete_test = self._build_completed_test(patient_age=66, access_token='tok-overview')

        response = self.client.get(
            reverse('doctor:patient_overview'),
            {'test_id': complete_test.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_test_id'], str(complete_test.id))
        self.assertTrue(response.context['completed_tests_for_select'])
        self.assertIn('Expected', response.context['performance_bands'])

    def test_patient_overview_export_filters_to_selected_test(self):
        self.client.login(username='demo_doctor', password='demo1234!')
        selected_test = self._build_completed_test(patient_age=66, access_token='tok-selected')
        self._build_completed_test(patient_age=40, access_token='tok-other')

        response = self.client.get(
            reverse('doctor:patient_overview_export'),
            {'test_id': selected_test.id},
        )

        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(StringIO(response.content.decode('utf-8-sig'))))
        self.assertEqual(rows[0], ['Report Type', 'Individual PPST Test Export'])
        self.assertIn(['Test ID', str(selected_test.id)], rows)
        self.assertIn(['Age Bracket', '61-75'], rows)
        self.assertIn([], rows)

        header_index = rows.index([
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

        first_data_row = rows[header_index + 1]
        self.assertEqual(first_data_row[3], selected_test.trials.order_by('trial_number').first().displayed_sequence)
        self.assertEqual(first_data_row[5], 'Exact match')
        self.assertEqual(first_data_row[6], 'Yes')

    def test_patient_overview_export_all_tests_includes_summary_and_trial_sections(self):
        self.client.login(username='demo_doctor', password='demo1234!')
        first_test = self._build_completed_test(patient_age=66, access_token='tok-all-1')
        second_test = self._build_completed_test(patient_age=40, access_token='tok-all-2')

        response = self.client.get(reverse('doctor:patient_overview_export'))

        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(StringIO(response.content.decode('utf-8-sig'))))
        self.assertEqual(rows[0], ['Report Type', 'All PPST Tests Export'])

        summary_header_index = rows.index([
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
        trial_header_index = rows.index([
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

        summary_rows = rows[summary_header_index + 1:trial_header_index - 1]
        exported_summary_ids = [row[0] for row in summary_rows]
        self.assertIn(str(first_test.id), exported_summary_ids)
        self.assertIn(str(second_test.id), exported_summary_ids)

        first_trial_row = rows[trial_header_index + 1]
        self.assertIn(first_trial_row[0], [str(first_test.id), str(second_test.id)])
        self.assertEqual(first_trial_row[6], 'Exact match')
        self.assertEqual(first_trial_row[7], 'Yes')

    def _build_completed_test(self, patient_age, access_token):
        test = Test.objects.create(
            doctor=self.doctor,
            patient_age=patient_age,
            access_token=access_token,
            status='COMPLETE',
            started_at=timezone.now() - timedelta(minutes=2),
            completed_at=timezone.now(),
        )
        generate_trials_for_test(test)
        first_trial = test.trials.order_by('trial_number').first()
        response = Response.objects.create(
            trial=first_trial,
            user_sequence=first_trial.displayed_sequence,
            is_exact_match=True,
            correct_positions=first_trial.span_length,
            accuracy=100.0,
            response_latency=1.5,
        )
        Keystroke.objects.create(response=response, key_pressed='3', position=1, latency=0.4)
        Keystroke.objects.create(response=response, key_pressed='1', position=2, latency=0.5)
        return test
