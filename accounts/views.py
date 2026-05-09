import logging
from threading import Thread

from django.conf import settings
from django.core.mail import send_mail
from django.db import close_old_connections

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from .throttles import AuthScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from .models import User, PasswordResetToken, EmailVerificationToken
from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    UserSerializer,
    AdminUserUpdateSerializer,
    ChangePasswordSerializer,
    GoogleOAuthSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
    DeleteAccountSerializer,
)
from .permissions import IsAdminUser

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────
# Async email helpers (non-blocking)
# ─────────────────────────────────────────────────────

def _send_email_background(subject, body, to_email):
    """Sends a single email in a background thread."""
    close_old_connections()
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=False)
        logger.info(f'Email sent: "{subject}" -> {to_email}')
    except Exception as e:
        logger.error(f'Email failed: "{subject}" -> {to_email}: {e}')
    close_old_connections()


def send_async_email(subject, body, to_email):
    """Fire-and-forget email dispatch via daemon thread."""
    thread = Thread(target=_send_email_background, args=(subject, body, to_email), daemon=True)
    thread.start()


def send_verification_email(user):
    """Creates a verification token and sends the verification email."""
    token = EmailVerificationToken.objects.create(user=user)
    verify_url = f'{settings.FRONTEND_URL}/verify-email?token={token.token}'
    send_async_email(
        'Verify Your Email — YesCab',
        (
            f'Hello {user.name},\n\n'
            f'Thank you for registering with YesCab! Please verify your email address '
            f'by clicking the link below:\n\n'
            f'{verify_url}\n\n'
            f'This link expires in {settings.EMAIL_VERIFY_TOKEN_EXPIRY_HOURS} hours.\n\n'
            f'If you did not create this account, please ignore this email.\n\n'
            f'— YesCab Team'
        ),
        user.email,
    )


# ─────────────────────────────────────────────────────
# Auth Views
# ─────────────────────────────────────────────────────

class RegisterView(generics.CreateAPIView):
    """
    POST /api/auth/register/
    Public endpoint. Creates a new user, sends verification email, returns JWT tokens.
    """
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_classes = [AuthScopedRateThrottle]
    throttle_scope = 'auth'

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Send verification email (non-blocking)
        send_verification_email(user)
        logger.info(f'New registration: {user.email}')

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                'message': 'Registration successful! Please check your email to verify your account.',
                'user': UserSerializer(user).data,
                'tokens': {
                    'access': str(refresh.access_token),
                    'refresh': str(refresh),
                },
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """
    POST /api/auth/login/
    Public endpoint. Validates credentials and returns JWT tokens + user info.
    """
    permission_classes = [AllowAny]
    throttle_classes = [AuthScopedRateThrottle]
    throttle_scope = 'auth'

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                'message': 'Login successful.',
                'user': UserSerializer(user).data,
                'tokens': {
                    'access': str(refresh.access_token),
                    'refresh': str(refresh),
                },
            }
        )


class LogoutView(APIView):
    """
    POST /api/auth/logout/
    Authenticated endpoint. Blacklists the refresh token to invalidate the session.
    Body: { "refresh": "<refresh_token>" }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response(
                {'error': 'Refresh token is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            return Response(
                {'error': 'Token is invalid or has already been blacklisted.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({'message': 'Logged out successfully.'}, status=status.HTTP_200_OK)


class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    GET  /api/auth/profile/ — Return current user's profile.
    PATCH /api/auth/profile/ — Update name, phone, place.
    """
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    """
    POST /api/auth/change-password/
    Authenticated. Allows user to change their own password securely.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'message': 'Password changed successfully.'})


# ─────────────────────────────────────────────────────
# Password Reset Views
# ─────────────────────────────────────────────────────

class ForgotPasswordView(APIView):
    """
    POST /api/auth/forgot-password/
    Public. Sends a password reset email. Always returns success to prevent enumeration.
    """
    permission_classes = [AllowAny]
    throttle_classes = [AuthScopedRateThrottle]
    throttle_scope = 'auth'

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email'].lower()

        # Always return success — do not reveal if email exists
        try:
            user = User.objects.get(email=email, is_active=True)
            # Invalidate any existing unused tokens
            PasswordResetToken.objects.filter(user=user, is_used=False).update(is_used=True)
            token = PasswordResetToken.objects.create(user=user)
            reset_url = f'{settings.FRONTEND_URL}/reset-password?token={token.token}'
            send_async_email(
                'Reset Your Password — YesCab',
                (
                    f'Hello {user.name},\n\n'
                    f'We received a request to reset your password. Click the link below:\n\n'
                    f'{reset_url}\n\n'
                    f'This link expires in {settings.PASSWORD_RESET_TOKEN_EXPIRY_HOURS} hour(s).\n\n'
                    f'If you did not request this, please ignore this email.\n\n'
                    f'— YesCab Team'
                ),
                user.email,
            )
            logger.info(f'Password reset token created for {email}')
        except User.DoesNotExist:
            logger.info(f'Password reset requested for non-existent email: {email}')

        return Response({
            'message': 'If an account with that email exists, a reset link has been sent.'
        })


class ResetPasswordView(APIView):
    """
    POST /api/auth/reset-password/
    Public. Validates token and sets new password.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token_uuid = serializer.validated_data['token']

        try:
            token_obj = PasswordResetToken.objects.select_related('user').get(token=token_uuid)
        except PasswordResetToken.DoesNotExist:
            return Response(
                {'error': 'Invalid or expired reset link.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not token_obj.is_valid():
            return Response(
                {'error': 'This reset link has expired or has already been used.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = token_obj.user
        user.set_password(serializer.validated_data['new_password'])
        user.save()

        token_obj.is_used = True
        token_obj.save()

        logger.info(f'Password reset completed for {user.email}')
        return Response({'message': 'Password reset successful. You can now log in.'})


# ─────────────────────────────────────────────────────
# Email Verification Views
# ─────────────────────────────────────────────────────

class VerifyEmailView(APIView):
    """
    POST /api/auth/verify-email/
    Public. Validates token and marks user email as verified.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        token_str = request.data.get('token')
        if not token_str:
            return Response(
                {'error': 'Verification token is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            import uuid
            token_uuid = uuid.UUID(str(token_str))
            token_obj = EmailVerificationToken.objects.select_related('user').get(token=token_uuid)
        except (ValueError, EmailVerificationToken.DoesNotExist):
            return Response(
                {'error': 'Invalid verification link.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not token_obj.is_valid():
            return Response(
                {'error': 'This verification link has expired or has already been used.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = token_obj.user
        user.is_email_verified = True
        user.save(update_fields=['is_email_verified'])

        token_obj.is_used = True
        token_obj.save()

        logger.info(f'Email verified for {user.email}')
        return Response({
            'message': 'Email verified successfully!',
            'user': UserSerializer(user).data,
        })


class ResendVerificationView(APIView):
    """
    POST /api/auth/resend-verification/
    Authenticated. Resends the verification email.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [AuthScopedRateThrottle]
    throttle_scope = 'auth'

    def post(self, request):
        user = request.user
        if user.is_email_verified:
            return Response({'message': 'Your email is already verified.'})

        # Invalidate old tokens
        EmailVerificationToken.objects.filter(user=user, is_used=False).update(is_used=True)
        send_verification_email(user)

        return Response({'message': 'Verification email sent. Please check your inbox.'})


# ─────────────────────────────────────────────────────
# Account Deletion
# ─────────────────────────────────────────────────────

class DeleteAccountView(APIView):
    """
    POST /api/auth/delete-account/
    Authenticated. Deletes the user's own account after password confirmation.
    Admin users cannot delete themselves via this endpoint.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user

        # Prevent admin self-deletion through this endpoint
        if user.is_admin:
            return Response(
                {'error': 'Admin accounts cannot be deleted via this endpoint. Contact another admin.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = DeleteAccountSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        email = user.email
        user.delete()

        logger.info(f'Account deleted by user: {email}')
        return Response({'message': 'Your account has been permanently deleted.'})


# ─────────────────────────────────────────────────────
# Admin Views
# ─────────────────────────────────────────────────────

class AdminUserListView(generics.ListAPIView):
    """
    GET /api/auth/admin/users/
    Admin only. Returns all users ordered by join date.
    """
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get_queryset(self):
        from django.db.models import Q

        queryset = User.objects.all().order_by('-date_joined')
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) | Q(email__icontains=search)
            )
        return queryset


class AdminUserDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /api/auth/admin/users/<pk>/
    PATCH  /api/auth/admin/users/<pk>/ — Update is_admin, is_active, etc.
    DELETE /api/auth/admin/users/<pk>/ — Delete user (self-delete blocked).
    """
    serializer_class = AdminUserUpdateSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    queryset = User.objects.all()

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        if user == request.user:
            return Response(
                {'error': 'You cannot delete your own account.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.delete()
        return Response({'message': 'User deleted successfully.'}, status=status.HTTP_200_OK)


class GoogleOAuthView(APIView):
    """
    POST /api/auth/google/
    Public endpoint. Receives a Google ID token (credential), verifies it,
    creates or retrieves the user, and issues JWT tokens.
    """
    permission_classes = [AllowAny]
    throttle_classes = [AuthScopedRateThrottle]
    throttle_scope = 'auth'

    def post(self, request):
        serializer = GoogleOAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        if not user.is_active:
            return Response(
                {'error': 'Your account has been deactivated. Contact support.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                'message': 'Google login successful.',
                'user': UserSerializer(user).data,
                'tokens': {
                    'access': str(refresh.access_token),
                    'refresh': str(refresh),
                },
            }
        )
