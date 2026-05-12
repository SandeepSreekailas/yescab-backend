from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from .models import User


def validate_indian_phone(value):
    import re
    if not value:
        raise serializers.ValidationError('Phone number is required.')
    val_str = str(value).strip()
    cleaned = re.sub(r'[\s\-\(\)\+]', '', val_str)
    if cleaned.startswith('91') and len(cleaned) == 12:
        cleaned = cleaned[2:]
    if not cleaned.isdigit():
        raise serializers.ValidationError('Phone number must contain only digits.')
    if len(cleaned) != 10:
        raise serializers.ValidationError('Phone number must be exactly 10 digits.')
    if cleaned[0] not in '6789':
        raise serializers.ValidationError('Indian mobile numbers must start with 6, 7, 8, or 9.')
    return f'+91 {cleaned}'


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
    agreed_to_terms = serializers.BooleanField(write_only=True)

    class Meta:
        model = User
        fields = ['name', 'email', 'phone', 'place', 'password', 'password2', 'agreed_to_terms']

    def validate_agreed_to_terms(self, value):
        if not value:
            raise serializers.ValidationError('You must agree to the Terms of Service and Privacy Policy.')
        return value

    def validate_email(self, value):
        if User.objects.filter(email=value.lower()).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value.lower()

    def validate_phone(self, value):
        return validate_indian_phone(value)

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({'password2': 'Passwords do not match.'})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        validated_data.pop('agreed_to_terms')
        password = validated_data.pop('password')
        user = User(**validated_data, is_email_verified=False)
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
        fields = ['id', 'name', 'email', 'phone', 'place', 'is_admin', 'is_active', 'is_email_verified', 'date_joined']
        read_only_fields = ['id', 'email', 'date_joined', 'is_admin', 'is_email_verified']

    def validate_phone(self, value):
        return validate_indian_phone(value)


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    """Serializer for admin to update user fields including is_admin and is_active."""

    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'phone', 'place', 'is_admin', 'is_active', 'is_email_verified', 'date_joined']
        read_only_fields = ['id', 'email', 'date_joined']

    def validate_phone(self, value):
        return validate_indian_phone(value)


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
            logger.error(f'Google token verification failed: {type(e).__name__}: {e}')
            raise serializers.ValidationError(
                'Google authentication failed. Please try again.'
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
                'is_email_verified': True,
            },
        )
        # If existing user, update name if blank
        if not created and not user.name:
            user.name = info['name']
            user.save(update_fields=['name'])

        # Ensure Google users are always email-verified
        if not user.is_email_verified:
            user.is_email_verified = True
            user.save(update_fields=['is_email_verified'])

        # Ensure user has an unusable password if created via OAuth
        if created:
            user.set_unusable_password()
            user.save()

        return user


class ForgotPasswordSerializer(serializers.Serializer):
    """Accepts email for password reset. Always succeeds to prevent user enumeration."""
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    """Validates reset token and sets new password."""
    token = serializers.UUIDField()
    new_password = serializers.CharField(
        write_only=True,
        min_length=8,
        validators=[validate_password],
        style={'input_type': 'password'}
    )
    new_password2 = serializers.CharField(write_only=True, style={'input_type': 'password'})

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password2']:
            raise serializers.ValidationError({'new_password2': 'Passwords do not match.'})
        return attrs


class DeleteAccountSerializer(serializers.Serializer):
    """Requires password confirmation to delete account."""
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})

    def validate_password(self, value):
        user = self.context['request'].user
        if user.has_usable_password() and not user.check_password(value):
            raise serializers.ValidationError('Password is incorrect.')
        return value
