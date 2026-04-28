from django.urls import path

from .views import attendance_action, dashboard

app_name = 'task'

urlpatterns = [
    path('', dashboard, name='dashboard'),
    path('attendance/action/', attendance_action, name='attendance_action'),
]
