from django.urls import path, include

urlpatterns = [
    path('', include('core.urls')),
    path('doctor/', include('doctor.urls')),
    path('patient/', include('patient.urls')),
]