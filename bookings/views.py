import logging
import resend
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

from threading import Thread
from django.db import close_old_connections


# ─────────────────────────────────────────────────────
# Background email dispatcher (non-blocking)
# ─────────────────────────────────────────────────────

def _send_booking_emails(email_data):
    """
    Runs in a background thread. Sends user confirmation + admin notification.
    Receives a plain dict (no ORM objects, no request) to guarantee thread safety.
    """
    close_old_connections()  # prevent stale DB connections in thread

    booking_id = email_data['booking_id']
    user_email = email_data['user_email']
    passenger_name = email_data['passenger_name']

    # 1. User confirmation email
    user_subject = f"Booking Confirmation #{booking_id} - YesCab"
    user_body = (
        f"Hello {passenger_name},\n\n"
        f"Your cab booking #{booking_id} has been received and is currently "
        f"pending admin approval. We will notify you once it's confirmed.\n\n"
        f"Thank you for choosing YesCab!"
    )

    try:
        if getattr(settings, 'RESEND_API_KEY', ''):
            resend.api_key = settings.RESEND_API_KEY
            r = resend.Emails.send({
                "from": settings.DEFAULT_FROM_EMAIL,
                "to": user_email,
                "subject": user_subject,
                "text": user_body,
            })
            logger.info(f"User confirmation email sent via Resend for booking #{booking_id}. ID: {getattr(r, 'id', r)}")
        else:
            logger.warning(f"RESEND_API_KEY is not set. Simulating user email via django send_mail.")
            send_mail(user_subject, user_body, settings.DEFAULT_FROM_EMAIL, [user_email], fail_silently=False)
            logger.info(f"User confirmation email printed to console for booking #{booking_id}")
    except Exception as e:
        logger.error(f"Failed to send user email (Resend/SMTP) for booking #{booking_id}: {e}")

    # 2. Admin notification email
    admin_email = email_data.get('admin_email')
    if admin_email:
        admin_subject = "New Booking Received - YesCab"
        admin_body = (
            f"A new booking has been received.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Booking ID    : #{booking_id}\n"
            f"Customer Name : {passenger_name}\n"
            f"Email         : {user_email}\n"
            f"Phone         : {email_data['phone_number']}\n"
            f"Trip Type     : {email_data['trip_type_display']}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Pickup        : {email_data['pickup']}\n"
            f"Drop          : {email_data['drop']}\n"
            f"Date          : {email_data['date']}\n"
            f"Time          : {email_data['time']}\n"
            f"Passengers    : {email_data['num_people']}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Please review and approve/reject this booking in the admin panel."
        )
        try:
            if getattr(settings, 'RESEND_API_KEY', ''):
                resend.api_key = settings.RESEND_API_KEY
                r = resend.Emails.send({
                    "from": settings.DEFAULT_FROM_EMAIL,
                    "to": admin_email,
                    "subject": admin_subject,
                    "text": admin_body,
                })
                logger.info(f"Admin notification sent via Resend for booking #{booking_id}. ID: {getattr(r, 'id', r)}")
            else:
                logger.warning(f"RESEND_API_KEY is not set. Simulating admin email via django send_mail.")
                send_mail(admin_subject, admin_body, settings.DEFAULT_FROM_EMAIL, [admin_email], fail_silently=False)
                logger.info(f"Admin notification printed to console for booking #{booking_id}")
        except Exception as e:
            logger.error(f"Failed to send admin notification (Resend/SMTP) for booking #{booking_id}: {e}")

    close_old_connections()  # clean up thread's DB connections


def dispatch_booking_emails(booking, user_email):
    """
    Extracts all data from the booking into a plain dict, then fires
    a daemon thread to send emails. The API returns immediately.
    """
    email_data = {
        'booking_id': booking.id,
        'user_email': user_email,
        'passenger_name': booking.name,
        'phone_number': booking.phone_number,
        'trip_type_display': booking.get_trip_type_display(),
        'pickup': booking.pickup_address or booking.from_location,
        'drop': booking.drop_address or booking.to_location,
        'date': str(booking.date),
        'time': str(booking.time),
        'num_people': booking.num_people,
        'admin_email': getattr(settings, 'ADMIN_EMAIL', ''),
    }

    thread = Thread(target=_send_booking_emails, args=(email_data,), daemon=True)
    thread.start()
    logger.info(f"Email thread dispatched for booking #{booking.id}")


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
        
        # Dispatch emails in background thread (non-blocking)
        dispatch_booking_emails(booking, request.user.email)

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
        from django.db.models import Q

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
                Q(name__icontains=search) |
                Q(user__email__icontains=search) |
                Q(from_location__icontains=search) |
                Q(to_location__icontains=search)
            )

        return queryset


def _send_status_change_email(email_data):
    """
    Background thread: notifies the user when their booking is approved or rejected.
    Receives a plain dict — no ORM objects, no request.
    """
    close_old_connections()

    booking_id = email_data['booking_id']
    new_status = email_data['new_status']
    user_email = email_data['user_email']

    if new_status == 'approved':
        subject = f"Your Booking is Confirmed \U0001f696 - YesCab #{booking_id}"
        status_line = "APPROVED ✅"
        closing = "Your cab has been confirmed. We look forward to serving you!"
    else:
        subject = f"Your Booking was Rejected \u274c - YesCab #{booking_id}"
        status_line = "REJECTED ❌"
        closing = "Unfortunately, we could not accommodate this booking. Please try again or contact support."

    body = (
        f"Hello {email_data['passenger_name']},\n\n"
        f"Your booking status has been updated.\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Booking ID : #{booking_id}\n"
        f"Status     : {status_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Pickup     : {email_data['pickup']}\n"
        f"Drop       : {email_data['drop']}\n"
        f"Date       : {email_data['date']}\n"
        f"Time       : {email_data['time']}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{closing}\n\n"
        f"Thank you for choosing YesCab!"
    )

    try:
        if getattr(settings, 'RESEND_API_KEY', ''):
            resend.api_key = settings.RESEND_API_KEY
            r = resend.Emails.send({
                "from": settings.DEFAULT_FROM_EMAIL,
                "to": user_email,
                "subject": subject,
                "text": body,
            })
            logger.info(f"Status change email ({new_status}) sent via Resend for booking #{booking_id}. ID: {getattr(r, 'id', r)}")
        else:
            logger.warning(f"RESEND_API_KEY is not set. Simulating status change email via django send_mail.")
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user_email], fail_silently=False)
            logger.info(f"Status change email ({new_status}) printed to console for booking #{booking_id}")
    except Exception as e:
        logger.error(f"Failed to send status change email (Resend/SMTP) for booking #{booking_id}: {e}")

    close_old_connections()


def dispatch_status_change_email(booking):
    """
    Extracts booking data into a plain dict and fires a daemon thread.
    Called only when status actually changes to approved/rejected.
    """
    email_data = {
        'booking_id': booking.id,
        'user_email': booking.user.email,
        'passenger_name': booking.name,
        'new_status': booking.status,
        'pickup': booking.pickup_address or booking.from_location,
        'drop': booking.drop_address or booking.to_location,
        'date': str(booking.date),
        'time': str(booking.time),
    }

    thread = Thread(target=_send_status_change_email, args=(email_data,), daemon=True)
    thread.start()
    logger.info(f"Status change email thread dispatched for booking #{booking.id}")


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

        old_status = booking.status

        serializer = BookingStatusSerializer(booking, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # Send email only if status actually changed to approved/rejected
        new_status = booking.status
        if new_status != old_status and new_status in ('approved', 'rejected'):
            try:
                dispatch_status_change_email(booking)
            except Exception as e:
                logger.error(f"Failed to dispatch status email for booking #{pk}: {e}")

        return Response(
            {
                'message': f'Booking #{pk} status updated to "{booking.status}".',
                'booking': BookingSerializer(booking).data,
            }
        )
