from django.urls import path
from . import views

app_name = 'patient'

urlpatterns = [
    path('<int:test_id>/', views.landing, name='landing'),
    path('<int:test_id>/written_instructions/', views.written_instructions, name='written_instructions'),
    path('<int:test_id>/instructions/', views.instructions, name='instructions'),
    path('<int:test_id>/practice-intro/', views.practice_intro, name='practice_intro'),
    path('<int:test_id>/practice/<int:question_num>/', views.practice, name='practice'),
    path('<int:test_id>/practice-complete/', views.practice_complete, name='practice_complete'),
    path('<int:test_id>/testing/', views.testing, name='testing'),
    path('<int:test_id>/abort/', views.abort_test, name='abort'),
    path('<int:test_id>/complete/', views.complete, name='complete'),
    path('test/<int:test_id>/export/', views.export_test_csv, name='export_csv'),
    path('export/all-tests/', views.export_all_tests_csv, name='export_all_tests'),
    path('export/age-groups/', views.export_age_group_csv, name='export_age_groups'),
]
