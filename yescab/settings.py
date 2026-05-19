from pathlib import Path
from datetime import timedelta
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

# ────────────────────────────────────────────────────────
# Core Settings (loaded from .env)
# ────────────────────────────────────────────────────────

SECRET_KEY = config('SECRET_KEY')

DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    # Local
    'accounts',
    'bookings',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'yescab.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# ────────────────────────────────────────────────────────
# Sentry Error Tracking (Production)
# ────────────────────────────────────────────────────────
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

SENTRY_DSN = config('SENTRY_DSN', default='')
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=True,
        environment='production' if not DEBUG else 'development'
    )

WSGI_APPLICATION = 'yescab.wsgi.application'

# ────────────────────────────────────────────────────────
# Database — SQLite for dev, PostgreSQL-ready for prod
# ────────────────────────────────────────────────────────



DB_ENGINE = config('DB_ENGINE', default='sqlite3')

if DB_ENGINE == 'postgresql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME'),
            'USER': config('DB_USER'),
            'PASSWORD': config('DB_PASSWORD'),
            'HOST': config('DB_HOST'),
            'PORT': config('DB_PORT', default='5432'),
            'OPTIONS': {
                'sslmode': 'require',  # 🔥 REQUIRED for Neon
                'connect_timeout': 10,
            },
            'CONN_MAX_AGE': 30,  # 🔥 keeps connection alive (important)
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / config('DB_NAME', default='db.sqlite3'),
        }
    }


AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom user model
AUTH_USER_MODEL = 'accounts.User'

# ────────────────────────────────────────────────────────
# Django REST Framework
# ────────────────────────────────────────────────────────

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.ScopedRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': config('ANON_THROTTLE_RATE', default='20/min'),
        'user': config('USER_THROTTLE_RATE', default='60/min'),
        'auth': config('AUTH_THROTTLE_RATE', default='5/15m'),
    },
    'EXCEPTION_HANDLER': 'yescab.exceptions.custom_exception_handler',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
}

# Simple JWT configuration
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
}

# ────────────────────────────────────────────────────────
# CORS — loaded from .env (comma-separated)
# ────────────────────────────────────────────────────────

CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:5173,http://127.0.0.1:5173',
    cast=Csv()
)
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='http://localhost:5173',
    cast=Csv()
)
CORS_ALLOW_CREDENTIALS = True

# ────────────────────────────────────────────────────────
# Email Configuration
# ────────────────────────────────────────────────────────

EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = config('EMAIL_HOST')
EMAIL_PORT = config('EMAIL_PORT', cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', cast=bool)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='onboarding@resend.dev')
ADMIN_EMAIL = config('ADMIN_EMAIL', default='')
RESEND_API_KEY = config('RESEND_API_KEY', default='')
ADMIN_WHATSAPP_NUMBER = config('ADMIN_WHATSAPP_NUMBER', default='')

# ────────────────────────────────────────────────────────
# Google OAuth2
# ────────────────────────────────────────────────────────

GOOGLE_OAUTH2_CLIENT_ID = config('GOOGLE_OAUTH2_CLIENT_ID', default='')

# ────────────────────────────────────────────────────────
# Frontend URL (for email links: verification, password reset)
# ────────────────────────────────────────────────────────

FRONTEND_URL = config('FRONTEND_URL', default='http://localhost:5173')

# Token expiry (hours)
PASSWORD_RESET_TOKEN_EXPIRY_HOURS = 0.5  # 30 minutes — industry best practice
EMAIL_VERIFY_TOKEN_EXPIRY_HOURS = 24

# ────────────────────────────────────────────────────────
# Payload size limit (5 MB)
# ────────────────────────────────────────────────────────

DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# ────────────────────────────────────────────────────────
# Production Security (only when DEBUG = False)
# ────────────────────────────────────────────────────────

if not DEBUG:
    # HTTPS enforcement
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

    # HSTS — tell browsers to always use HTTPS (1 year)
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    # Secure cookies — only sent over HTTPS
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    # Prevent clickjacking
    X_FRAME_OPTIONS = 'DENY'

    # Prevent MIME-type sniffing
    SECURE_CONTENT_TYPE_NOSNIFF = True

# ────────────────────────────────────────────────────────
# Structured Logging
# ────────────────────────────────────────────────────────

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] [{levelname}] [{name}] {message}',
            'style': '{',
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
        },
        'django.security': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'accounts': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'bookings': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Monkey-patch DRF's SimpleRateThrottle to support multiplied periods like '15m'
try:
    from rest_framework.throttling import SimpleRateThrottle
    import re

    original_parse_rate = SimpleRateThrottle.parse_rate

    def custom_parse_rate(self, rate):
        if rate is None:
            return (None, None)
        num, period = rate.split('/')
        match = re.match(r'^(\d+)([smhd])$', period)
        if match:
            multiplier = int(match.group(1))
            unit = match.group(2)
            base = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[unit]
            return (int(num), base * multiplier)
        return original_parse_rate(self, rate)

    SimpleRateThrottle.parse_rate = custom_parse_rate
except ImportError:
    pass
