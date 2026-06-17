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


class PatientFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='doc2', password='pass12345')
        self.doctor = Doctor.objects.create(user=self.user)
        self.test_obj = Test.objects.create(doctor=self.doctor, patient_age=70, access_token='token-123')

    def test_landing_page_loads(self):
        response = self.client.get(reverse('patient:landing', args=[self.test_obj.id]))
        self.assertEqual(response.status_code, 200)

    def test_submit_marks_test_complete(self):
        url = reverse('patient:testing', args=[self.test_obj.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

        self.test_obj.refresh_from_db()
        self.assertEqual(self.test_obj.status, 'COMPLETE')
        self.assertIsNotNone(self.test_obj.completed_at)

    def test_export_test_csv_requires_doctor_login(self):
        response = self.client.get(reverse('patient:export_csv', args=[self.test_obj.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_export_test_csv_includes_summary_and_trial_details(self):
        self.client.login(username='doc2', password='pass12345')
        export_test = self._build_completed_test(self.doctor, patient_age=70, access_token='token-export')

        response = self.client.get(reverse('patient:export_csv', args=[export_test.id]))

        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(StringIO(response.content.decode('utf-8-sig'))))
        self.assertEqual(rows[0], ['Report Type', 'Individual PPST Test Export'])
        self.assertIn(['Age Bracket', '61-75'], rows)
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
        self.assertEqual(first_data_row[3], export_test.trials.order_by('trial_number').first().displayed_sequence)
        self.assertEqual(first_data_row[5], 'Exact match')
        self.assertEqual(first_data_row[6], 'Yes')

    def test_export_all_tests_csv_only_includes_logged_in_doctor_tests(self):
        other_user = User.objects.create_user(username='doc3', password='pass12345')
        other_doctor = Doctor.objects.create(user=other_user)
        owned_test = self._build_completed_test(self.doctor, patient_age=70, access_token='token-owned')
        other_test = self._build_completed_test(other_doctor, patient_age=45, access_token='token-other')
        self.client.login(username='doc2', password='pass12345')

        response = self.client.get(reverse('patient:export_all_tests'))

        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(StringIO(response.content.decode('utf-8-sig'))))
        exported_test_ids = [row[0] for row in rows[1:]]
        self.assertIn(str(owned_test.id), exported_test_ids)
        self.assertNotIn(str(other_test.id), exported_test_ids)
        self.assertEqual(rows[0][:4], ['Test ID', 'Patient Age', 'Age Bracket', 'Test Status'])

    def test_export_age_group_csv_filters_by_requested_bracket(self):
        self.client.login(username='doc2', password='pass12345')
        matching_test = self._build_completed_test(self.doctor, patient_age=70, access_token='token-match')
        non_matching_test = self._build_completed_test(self.doctor, patient_age=34, access_token='token-nonmatch')

        response = self.client.get(
            reverse('patient:export_age_groups'),
            {'age_bracket': '61-75'},
        )

        self.assertEqual(response.status_code, 200)
        rows = list(csv.reader(StringIO(response.content.decode('utf-8-sig'))))
        exported_test_ids = [row[0] for row in rows[1:]]
        self.assertIn(str(matching_test.id), exported_test_ids)
        self.assertNotIn(str(non_matching_test.id), exported_test_ids)

    def _build_completed_test(self, doctor, patient_age, access_token):
        test = Test.objects.create(
            doctor=doctor,
            patient_age=patient_age,
            access_token=access_token,
            status='COMPLETE',
            started_at=timezone.now() - timedelta(minutes=3),
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
            response_latency=1.75,
        )
        Keystroke.objects.create(response=response, key_pressed='3', position=1, latency=0.4)
        Keystroke.objects.create(response=response, key_pressed='1', position=2, latency=0.6)
        return test
