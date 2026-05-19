from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse


def health_check(request):
    """Lightweight health check for uptime monitoring and load balancers."""
    return JsonResponse({'status': 'ok'}, status=200)


urlpatterns = [
    path('yescab-ops-panel/', admin.site.urls),  # Obfuscated — not at /admin/
    path('api/health/', health_check, name='health_check'),
    path('api/auth/', include('accounts.urls')),
    path('api/bookings/', include('bookings.urls')),
]
