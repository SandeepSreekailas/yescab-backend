import logging
import resend
from django.core.mail import send_mail
from django.conf import settings
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from .models import Booking, Vehicle
from .serializers import BookingSerializer, BookingStatusSerializer, VehicleSerializer
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
        queryset = Booking.objects.filter(user=self.request.user).select_related('vehicle').order_by('-created_at')
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset

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
    lookup_field = 'public_id'

    def get_queryset(self):
        return Booking.objects.filter(user=self.request.user).select_related('vehicle')


# ─────────────────────────────────────────────────────
# Admin Views
# ─────────────────────────────────────────────────────

class VehicleListView(generics.ListAPIView):
    """
    GET /api/bookings/admin/vehicles/
    Admin only. Returns all vehicles for assignment.
    """
    serializer_class = VehicleSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    queryset = Vehicle.objects.all()
    pagination_class = None

class AdminBookingListView(generics.ListAPIView):
    """
    GET /api/bookings/admin/all/
    Admin only. Returns all bookings with optional ?status= and ?trip_type= filters.
    """
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get_queryset(self):
        from django.db.models import Q

        queryset = Booking.objects.all().select_related('user', 'vehicle').order_by('-created_at')

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


class UserStatsView(APIView):
    """
    GET /api/bookings/stats/
    Returns aggregated counts for the authenticated user's dashboard StatsBar.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Count, Q
        
        stats = Booking.objects.filter(user=request.user).aggregate(
            total_bookings=Count('id'),
            pending=Count('id', filter=Q(status='pending')),
            approved=Count('id', filter=Q(status='approved')),
            driver_assigned=Count('id', filter=Q(status='driver_assigned')),
            completed=Count('id', filter=Q(status='completed')),
            rejected=Count('id', filter=Q(status='rejected')),
            cancelled=Count('id', filter=Q(status='cancelled')),
        )
        
        return Response(stats)


class AdminStatsView(APIView):
    """
    GET /api/bookings/admin/stats/
    Returns aggregated counts for dashboard StatsBar.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        from accounts.models import User
        from django.db.models import Count, Q
        
        users_count = User.objects.count()
        
        stats = Booking.objects.aggregate(
            total_bookings=Count('id'),
            pending=Count('id', filter=Q(status='pending')),
            approved=Count('id', filter=Q(status='approved')),
            driver_assigned=Count('id', filter=Q(status='driver_assigned')),
            completed=Count('id', filter=Q(status='completed')),
            rejected=Count('id', filter=Q(status='rejected')),
            cancelled=Count('id', filter=Q(status='cancelled')),
        )
        
        stats['users'] = users_count
        return Response(stats)


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
    elif new_status == 'driver_assigned':
        subject = f"Driver Assigned to Your Booking \U0001f698 - YesCab #{booking_id}"
        status_line = "DRIVER ASSIGNED 🚖"
        closing = "A driver has been assigned to your booking. Have a safe journey!"
    elif new_status == 'completed':
        subject = f"Booking Completed \U0001f3c1 - YesCab #{booking_id}"
        status_line = "COMPLETED 🏁"
        closing = "Your trip is completed. Thank you for riding with YesCab!"
    elif new_status == 'cancelled':
        subject = f"Booking Cancelled \u26a0\ufe0f - YesCab #{booking_id}"
        status_line = "CANCELLED ✋"
        closing = "Your booking has been cancelled as requested. We hope to see you again soon."
    else:
        subject = f"Your Booking was Rejected \u274c - YesCab #{booking_id}"
        status_line = "REJECTED ❌"
        closing = "Unfortunately, we could not accommodate this booking. Please try again or contact support."

    admin_note = email_data.get('admin_note')
    rejection_reason = email_data.get('rejection_reason')
    
    admin_note_section = ""
    if admin_note or (new_status == 'rejected' and rejection_reason):
        admin_note_section += f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        if new_status == 'rejected' and rejection_reason:
            admin_note_section += f"Rejection Reason: {rejection_reason}\n"
        if admin_note:
            admin_note_section += f"Admin Note : {admin_note}\n"

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
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{admin_note_section}"
        f"\n{closing}\n\n"
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
    Called only when status actually changes.
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
        'admin_note': booking.admin_note,
        'rejection_reason': booking.rejection_reason,
    }

    thread = Thread(target=_send_status_change_email, args=(email_data,), daemon=True)
    thread.start()
    logger.info(f"Status change email thread dispatched for booking #{booking.id}")


class AdminBookingStatusView(APIView):
    """
    PATCH /api/bookings/admin/<public_id>/status/
    Admin only. Update booking status with strict state-machine enforcement.
    Finalized bookings (completed/rejected/cancelled) cannot be modified.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    def patch(self, request, public_id):
        try:
            booking = Booking.objects.select_related('user').get(public_id=public_id)
        except Booking.DoesNotExist:
            return Response(
                {'error': f'Booking #{public_id} not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Guard: block all modifications on finalized bookings
        TERMINAL = {'completed', 'rejected', 'cancelled'}
        if booking.status in TERMINAL:
            label = 'cancelled by customer' if booking.status == 'cancelled' else booking.status
            return Response(
                {'error': f'Booking #{public_id} is {label} and cannot be modified.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_status = booking.status

        serializer = BookingStatusSerializer(booking, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # Send email only if status actually changed
        new_status = booking.status
        if new_status != old_status:
            try:
                dispatch_status_change_email(booking)
            except Exception as e:
                logger.error(f"Failed to dispatch status email for booking #{pk}: {e}")

        return Response(
            {
                'message': f'Booking #{public_id} status updated to "{booking.get_status_display()}".',
                'booking': BookingSerializer(booking).data,
            }
        )


class BookingCancelView(APIView):
    """
    POST /api/bookings/<public_id>/cancel/
    User only. Cancel own booking if it's in a cancellable state.
    Valid cancellable states: pending, approved, driver_assigned.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, public_id):
        try:
            booking = Booking.objects.select_related('user').get(public_id=public_id, user=request.user)
        except Booking.DoesNotExist:
            return Response(
                {'error': f'Booking #{public_id} not found or you do not have permission to cancel it.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        CANCELLABLE = {'pending', 'approved', 'driver_assigned'}
        if booking.status not in CANCELLABLE:
            status_labels = {
                'completed': 'This ride has already been completed.',
                'rejected': 'This booking was already rejected by admin.',
                'cancelled': 'This booking has already been cancelled.',
            }
            msg = status_labels.get(booking.status, f'Booking cannot be cancelled from "{booking.status}" state.')
            return Response(
                {'error': msg},
                status=status.HTTP_400_BAD_REQUEST,
            )

        booking.status = 'cancelled'
        booking.cancelled_at = timezone.now()
        booking.save()

        # Notify user and admin about cancellation
        dispatch_status_change_email(booking)

        return Response(
            {
                'message': f'Booking #{public_id} has been cancelled successfully.',
                'booking': BookingSerializer(booking).data,
            }
        )

