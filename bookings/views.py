from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from .models import Booking
from .serializers import BookingSerializer, BookingStatusSerializer
from accounts.permissions import IsAdminUser


class BookingListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/bookings/ — List all bookings belonging to the authenticated user.
    POST /api/bookings/ — Create a new booking for the authenticated user.
    """
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Booking.objects.filter(user=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
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
