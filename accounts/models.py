import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone


class UserManager(BaseUserManager):
    """Custom manager for User model with email as the username field."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('An email address is required.')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_admin', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model that uses email as the unique identifier instead of username.
    Includes name, phone, place fields and an is_admin flag for role-based access.
    """
    name = models.CharField(max_length=150, verbose_name='Full Name')
    email = models.EmailField(unique=True, verbose_name='Email Address')
    phone = models.CharField(max_length=20, verbose_name='Phone Number')
    place = models.CharField(max_length=100, verbose_name='Place / City')
    is_admin = models.BooleanField(
        default=False,
        help_text='Grants access to the custom admin dashboard.'
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(
        default=True,
        help_text='True = existing/Google users. New registrations set to False until verified.'
    )
    pending_email = models.EmailField(
        blank=True, null=True,
        help_text='Stores new email until it is verified.'
    )
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name']

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-date_joined']

    def __str__(self):
        return f'{self.name} <{self.email}>'

    def get_full_name(self):
        return self.name

    def get_short_name(self):
        return self.name.split()[0] if self.name else self.email


class PasswordResetToken(models.Model):
    """Secure token for password reset flow. Expires after configured hours."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_reset_tokens')
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'PasswordReset for {self.user.email} ({"used" if self.is_used else "active"})'

    def is_expired(self):
        from django.conf import settings
        expiry_hours = getattr(settings, 'PASSWORD_RESET_TOKEN_EXPIRY_HOURS', 1)
        from datetime import timedelta
        return timezone.now() > self.created_at + timedelta(hours=expiry_hours)

    def is_valid(self):
        return not self.is_used and not self.is_expired()


class EmailVerificationToken(models.Model):
    """Secure token for email verification. Expires after configured hours."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_verification_tokens')
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'EmailVerify for {self.user.email} ({"used" if self.is_used else "active"})'

    def is_expired(self):
        from django.conf import settings
        expiry_hours = getattr(settings, 'EMAIL_VERIFY_TOKEN_EXPIRY_HOURS', 24)
        from datetime import timedelta
        return timezone.now() > self.created_at + timedelta(hours=expiry_hours)

    def is_valid(self):
        return not self.is_used and not self.is_expired()
