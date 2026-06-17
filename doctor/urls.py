from django.urls import path
from . import views

app_name = 'doctor'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('tests/info/', views.test_info, name='test_info'),
    path('tests/create/', views.create_test, name='create_test'),
    path('tests/<int:test_id>/delete/', views.delete_test,name='delete_test'),
    path('tests/<int:test_id>/details/', views.test_details, name='test_details'),
    path('patient-overview/', views.patient_overview, name='patient_overview'),
    path('patient-overview/export/', views.export_patient_overview_csv, name='patient_overview_export'),
    #path('test-info/', views.test_info, name='test_info'),
]
