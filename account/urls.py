from django.contrib.auth.views import LogoutView
from django.urls import path

from .views import CustomLoginView, employee_management, leaves, profile

app_name = 'account'

urlpatterns = [
    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('profile/', profile, name='profile'),
    path('leaves/', leaves, name='leaves'),
    path('employees/', employee_management, name='employee_management'),
]
