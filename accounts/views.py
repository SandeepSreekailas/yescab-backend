from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from .models import User
from .serializers import (
    RegisterSerializer,
    LoginSerializer,
    UserSerializer,
    AdminUserUpdateSerializer,
    ChangePasswordSerializer,
    GoogleOAuthSerializer,
)
from .permissions import IsAdminUser


class RegisterView(generics.CreateAPIView):
    """
    POST /api/auth/register/
    Public endpoint. Creates a new user and returns JWT tokens immediately.
    """
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                'message': 'Registration successful. Welcome to YesCab!',
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
        queryset = User.objects.all().order_by('-date_joined')
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search) | queryset.filter(email__icontains=search)
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
