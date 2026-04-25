from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from .models import User


class RegisterSerializer(serializers.ModelSerializer):
    """Serializer for new user registration with password confirmation."""
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        validators=[validate_password],
        style={'input_type': 'password'}
    )
    password2 = serializers.CharField(
        write_only=True,
        label='Confirm Password',
        style={'input_type': 'password'}
    )

    class Meta:
        model = User
        fields = ['name', 'email', 'phone', 'place', 'password', 'password2']

    def validate_email(self, value):
        if User.objects.filter(email=value.lower()).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value.lower()

    def validate_phone(self, value):
        import re
        cleaned = re.sub(r'[\s\-\(\)\+]', '', value)
        if not cleaned.isdigit() or not (7 <= len(cleaned) <= 15):
            raise serializers.ValidationError('Enter a valid phone number (7–15 digits).')
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({'password2': 'Passwords do not match.'})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    """Serializer for user login — validates credentials and returns user object."""
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})

    def validate(self, attrs):
        email = attrs.get('email', '').lower()
        password = attrs.get('password')

        user = authenticate(
            request=self.context.get('request'),
            username=email,
            password=password
        )

        if not user:
            raise serializers.ValidationError('Invalid email or password. Please try again.')
        if not user.is_active:
            raise serializers.ValidationError('Your account has been deactivated. Contact support.')

        attrs['user'] = user
        return attrs


class UserSerializer(serializers.ModelSerializer):
    """Safe serializer for reading/updating user info (no password exposed)."""

    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'phone', 'place', 'is_admin', 'is_active', 'date_joined']
        read_only_fields = ['id', 'email', 'date_joined', 'is_admin']


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    """Serializer for admin to update user fields including is_admin and is_active."""

    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'phone', 'place', 'is_admin', 'is_active', 'date_joined']
        read_only_fields = ['id', 'email', 'date_joined']


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for authenticated users to change their own password."""
    old_password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    new_password = serializers.CharField(
        write_only=True,
        min_length=8,
        validators=[validate_password],
        style={'input_type': 'password'}
    )
    new_password2 = serializers.CharField(write_only=True, style={'input_type': 'password'})

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Old password is incorrect.')
        return value

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({'new_password2': 'New passwords do not match.'})
        return attrs

    def save(self):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user


class GoogleOAuthSerializer(serializers.Serializer):
    """
    Serializer for Google OAuth login.
    Accepts a Google ID token, verifies it, and returns (or creates) a user.
    """
    credential = serializers.CharField(
        help_text='The Google ID token (credential) from the frontend.'
    )

    def validate_credential(self, value):
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests
        from django.conf import settings
        import logging

        logger = logging.getLogger(__name__)

        try:
            id_info = id_token.verify_oauth2_token(
                value,
                google_requests.Request(),
                settings.GOOGLE_OAUTH2_CLIENT_ID.strip(),
                clock_skew_in_seconds=60,
            )
        except Exception as e:
            print(f'\n[GOOGLE AUTH ERROR] {type(e).__name__}: {e}\n')
            logger.error(f'Google token verification failed: {type(e).__name__}: {e}')
            raise serializers.ValidationError(
                f'Google token verification failed: {e}'
            )

        # Ensure the token is from Google
        if id_info.get('iss') not in ('accounts.google.com', 'https://accounts.google.com'):
            raise serializers.ValidationError('Invalid token issuer.')

        email = id_info.get('email')
        if not email:
            raise serializers.ValidationError('Google account has no email address.')

        if not id_info.get('email_verified', False):
            raise serializers.ValidationError('Google email is not verified.')

        self.google_info = {
            'email': email.lower(),
            'name': id_info.get('name', email.split('@')[0]),
            'picture': id_info.get('picture', ''),
        }

        return value

    def create(self, validated_data):
        """Get or create a user from the verified Google profile."""
        info = self.google_info
        user, created = User.objects.get_or_create(
            email=info['email'],
            defaults={
                'name': info['name'],
                'phone': '',
                'place': '',
            },
        )
        # If existing user, update name if blank
        if not created and not user.name:
            user.name = info['name']
            user.save(update_fields=['name'])

        # Ensure user has an unusable password if created via OAuth
        if created:
            user.set_unusable_password()
            user.save()

        return user
