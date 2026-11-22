from django.urls import path

from .views import (
    GuestView, LoginView, LogoutView, ProfileView, RefreshView, SignUpView, UsernameAvailableView,
)

urlpatterns = [
    path("username-available/", UsernameAvailableView.as_view()),
    path("signup/", SignUpView.as_view()),
    path("login/", LoginView.as_view()),
    path("refresh/", RefreshView.as_view()),
    path("logout/", LogoutView.as_view()),
    path("guest/", GuestView.as_view()),
    path("me/", ProfileView.as_view()),
]