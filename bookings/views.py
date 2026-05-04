import logging
from django.core.mail import send_mail
from django.conf import settings
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from .models import Booking
from .serializers import BookingSerializer, BookingStatusSerializer
from accounts.permissions import IsAdminUser

logger = logging.getLogger(__name__)

from django.utils import timezone
from datetime import timedelta

# EMAIL FAILURE CRASH FIX: Safe synchronous email sending with exception handling
def send_booking_email_safe(user_email, booking_id, passenger_name):
    try:
        subject = f"Booking Confirmation #{booking_id} - YesCab"
        message = f"Hello {passenger_name},\n\nYour cab booking #{booking_id} has been received and is currently pending admin approval. We will notify you once it's confirmed.\n\nThank you for choosing YesCab!"
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user_email],
            fail_silently=False,
        )
    except Exception as e:
        # Fails silently, logs the error, but does NOT crash the API
        logger.error(f"Failed to send booking email for booking #{booking_id}: {str(e)}")


class BookingListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/bookings/ — List all bookings belonging to the authenticated user.
    POST /api/bookings/ — Create a new booking for the authenticated user.
    """
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # CROSS-USER DATA ACCESS FIX: Strictly limits to authenticated user
        return Booking.objects.filter(user=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        # Automatically assign user to prevent user-injection
        return serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        # Prevent duplicate bookings: check if same user created a booking in the last 10 seconds
        time_threshold = timezone.now() - timedelta(seconds=10)
        recent_booking = Booking.objects.filter(
            user=request.user,
            created_at__gte=time_threshold
        ).exists()
        
        if recent_booking:
            return Response(
                {"error": "Please wait a few seconds before creating another booking."},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = self.perform_create(serializer)
        
        # Dispatch email safely (synchronous but wrapped in try/except)
        send_booking_email_safe(request.user.email, booking.id, booking.name)

        return Response(
            {
                'message': 'Booking created successfully! We will confirm shortly.',
                'booking': serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )


class BookingDetailView(generics.RetrieveAPIView):
    """
    GET /api/bookings/<pk>/
    Returns a single booking — only if it belongs to the authenticated user.
    """
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Booking.objects.filter(user=self.request.user)


# ─────────────────────────────────────────────────────
# Admin Views
# ─────────────────────────────────────────────────────

class AdminBookingListView(generics.ListAPIView):
    """
    GET /api/bookings/admin/all/
    Admin only. Returns all bookings with optional ?status= and ?trip_type= filters.
    """
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get_queryset(self):
        queryset = Booking.objects.all().select_related('user').order_by('-created_at')

        status_filter = self.request.query_params.get('status')
        trip_type_filter = self.request.query_params.get('trip_type')
        search = self.request.query_params.get('search')

        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if trip_type_filter:
            queryset = queryset.filter(trip_type=trip_type_filter)
        if search:
            queryset = queryset.filter(
                name__icontains=search
            ) | queryset.filter(
                user__email__icontains=search
            ) | queryset.filter(
                from_location__icontains=search
            ) | queryset.filter(
                to_location__icontains=search
            )

        return queryset


class AdminBookingStatusView(APIView):
    """
    PATCH /api/bookings/admin/<pk>/status/
    Admin only. Update booking status to approved or rejected, with optional notes.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    def patch(self, request, pk):
        try:
            booking = Booking.objects.select_related('user').get(pk=pk)
        except Booking.DoesNotExist:
            return Response(
                {'error': f'Booking #{pk} not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = BookingStatusSerializer(booking, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                'message': f'Booking #{pk} status updated to "{booking.status}".',
                'booking': BookingSerializer(booking).data,
            }
        )
