from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    RegisterView,
    LoginView,
    LogoutView,
    UserProfileView,
    ChangePasswordView,
    AdminUserListView,
    AdminUserDetailView,
    GoogleOAuthView,
    ForgotPasswordView,
    ResetPasswordView,
    VerifyEmailView,
    ResendVerificationView,
    DeleteAccountView,
    ChangeEmailView,
)

urlpatterns = [
    # Authentication
    path('register/', RegisterView.as_view(), name='auth_register'),
    path('login/', LoginView.as_view(), name='auth_login'),
    path('logout/', LogoutView.as_view(), name='auth_logout'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('google/', GoogleOAuthView.as_view(), name='auth_google'),

    # Password reset
    path('forgot-password/', ForgotPasswordView.as_view(), name='auth_forgot_password'),
    path('reset-password/', ResetPasswordView.as_view(), name='auth_reset_password'),

    # Email verification
    path('verify-email/', VerifyEmailView.as_view(), name='auth_verify_email'),
    path('resend-verification/', ResendVerificationView.as_view(), name='auth_resend_verification'),

    # User profile
    path('profile/', UserProfileView.as_view(), name='auth_profile'),
    path('change-password/', ChangePasswordView.as_view(), name='auth_change_password'),
    path('change-email/', ChangeEmailView.as_view(), name='auth_change_email'),
    path('delete-account/', DeleteAccountView.as_view(), name='auth_delete_account'),

    # Admin — user management
    path('admin/users/', AdminUserListView.as_view(), name='admin_user_list'),
    path('admin/users/<int:pk>/', AdminUserDetailView.as_view(), name='admin_user_detail'),
]
