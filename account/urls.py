from django.contrib.auth.views import LogoutView
from django.urls import path

from .views import (
    CustomLoginView, attendances, chat_list, chat_poll, chat_send,
    chat_unread_count, chat_unread_per_user, chat_with, detect_my_ip, edit_profile,
    employee_management, leave_management, leaves, pending_leaves_count,
    positions_management, profile, site_settings,
)

app_name = 'account'

urlpatterns = [
    path('login/', CustomLoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('profile/', profile, name='profile'),
    path('profile/edit/', edit_profile, name='edit_profile'),
    path('attendances/', attendances, name='attendances'),
    path('leaves/', leaves, name='leaves'),
    path('leaves/manage/', leave_management, name='leave_management'),
    path('leaves/pending-count/', pending_leaves_count, name='pending_leaves_count'),
    path('employees/', employee_management, name='employee_management'),
    path('settings/', site_settings, name='site_settings'),
    path('settings/detect-ip/', detect_my_ip, name='detect_my_ip'),
    path('positions/', positions_management, name='positions_management'),
    # Chat
    path('chat/', chat_list, name='chat_list'),
    path('chat/<int:user_id>/', chat_with, name='chat_with'),
    path('chat/<int:user_id>/send/', chat_send, name='chat_send'),
    path('chat/<int:user_id>/poll/', chat_poll, name='chat_poll'),
    path('chat/unread/', chat_unread_count, name='chat_unread'),
    path('chat/unread/per-user/', chat_unread_per_user, name='chat_unread_per_user'),
]
