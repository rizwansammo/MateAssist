from django.urls import path

from .views import (
    AccountView,
    LoginView,
    LogoutView,
    MeView,
    PasswordChangeView,
    RefreshView,
)

app_name = "accounts"

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/refresh/", RefreshView.as_view(), name="refresh"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("account/", AccountView.as_view(), name="account"),
    path("account/password/", PasswordChangeView.as_view(), name="account-password"),
]
