from rest_framework import serializers
from django.utils import timezone
from .models import Booking, Vehicle
from accounts.serializers import UserSerializer

class VehicleSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    class Meta:
        model = Vehicle
        fields = ['id', 'name', 'status', 'status_display']

# ── Valid state transitions (source of truth for entire system) ──
VALID_TRANSITIONS = {
    'pending':         ['approved', 'rejected', 'cancelled'],
    'approved':        ['driver_assigned', 'completed', 'cancelled'],
    'driver_assigned': ['completed', 'cancelled'],
    'completed':       [],   # Terminal state
    'rejected':        [],   # Terminal state
    'cancelled':       [],   # Terminal state
}

TERMINAL_STATES = {'completed', 'rejected', 'cancelled'}


class BookingSerializer(serializers.ModelSerializer):
    """
    Full booking serializer. Includes display-friendly fields for trip type and status.
    User is set automatically from the request; read-only for API consumers.
    """
    user_info = UserSerializer(source='user', read_only=True)
    trip_type_display = serializers.CharField(source='get_trip_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)
    is_finalized = serializers.SerializerMethodField()
    vehicle_info = VehicleSerializer(source='vehicle', read_only=True)

    class Meta:
        model = Booking
        fields = [
            'id',
            'user',
            'user_info',
            'trip_type',
            'trip_type_display',
            'name',
            'phone_number',
            'num_people',
            'from_location',
            'to_location',
            'pickup_address',
            'pickup_lat',
            'pickup_lng',
            'drop_address',
            'drop_lat',
            'drop_lng',
            'date',
            'time',
            'notes',
            'status',
            'status_display',
            'admin_note',
            'rejection_reason',
            'vehicle',
            'vehicle_info',
            'expected_duration_hours',
            'cancelled_at',
            'is_finalized',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'user', 'status', 'admin_note', 'rejection_reason', 'vehicle', 'cancelled_at', 'is_finalized', 'created_at', 'updated_at']

    def get_is_finalized(self, obj):
        """Returns True if booking is in a terminal state (no further changes allowed)."""
        return obj.status in TERMINAL_STATES

    def validate_num_people(self, value):
        if value < 1:
            raise serializers.ValidationError('At least 1 passenger is required.')
        if value > 50:
            raise serializers.ValidationError('Maximum 50 passengers per booking.')
        return value

    def validate_phone_number(self, value):
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

    def validate_from_location(self, value):
        if len(value.strip()) < 3:
            raise serializers.ValidationError('Pickup location must be at least 3 characters.')
        return value.strip()

    def validate_to_location(self, value):
        if len(value.strip()) < 3:
            raise serializers.ValidationError('Drop location must be at least 3 characters.')
        return value.strip()

    def validate_pickup_lat(self, value):
        if value is not None and not (-90 <= value <= 90):
            raise serializers.ValidationError('Latitude must be between -90 and 90.')
        return value

    def validate_pickup_lng(self, value):
        if value is not None and not (-180 <= value <= 180):
            raise serializers.ValidationError('Longitude must be between -180 and 180.')
        return value

    def validate_drop_lat(self, value):
        if value is not None and not (-90 <= value <= 90):
            raise serializers.ValidationError('Latitude must be between -90 and 90.')
        return value

    def validate_drop_lng(self, value):
        if value is not None and not (-180 <= value <= 180):
            raise serializers.ValidationError('Longitude must be between -180 and 180.')
        return value

    def validate_date(self, value):
        from dateutil.relativedelta import relativedelta
        today = timezone.now().date()
        if value < today:
            raise serializers.ValidationError('Travel date cannot be in the past.')
        max_date = today + relativedelta(months=6)
        if value > max_date:
            raise serializers.ValidationError(
                f'Booking allowed only within the next 6 months (until {max_date}).'
            )
        return value

    def validate(self, attrs):
        from_loc = attrs.get('from_location', '')
        to_loc = attrs.get('to_location', '')
        if from_loc.lower() == to_loc.lower():
            raise serializers.ValidationError(
                {'to_location': 'Pickup and drop locations cannot be the same.'}
            )

        # If coordinates are provided, validate they are complete pairs
        pickup_lat = attrs.get('pickup_lat')
        pickup_lng = attrs.get('pickup_lng')
        if (pickup_lat is not None) != (pickup_lng is not None):
            raise serializers.ValidationError(
                {'pickup_lat': 'Both pickup latitude and longitude must be provided together.'}
            )

        drop_lat = attrs.get('drop_lat')
        drop_lng = attrs.get('drop_lng')
        if (drop_lat is not None) != (drop_lng is not None):
            raise serializers.ValidationError(
                {'drop_lat': 'Both drop latitude and longitude must be provided together.'}
            )

        # ── Ernakulam geo-restriction (must match frontend bounding box) ──
        ERNAKULAM = {'min_lat': 9.7, 'max_lat': 10.2, 'min_lng': 76.1, 'max_lng': 76.5}

        for prefix, label in [('pickup', 'Pickup'), ('drop', 'Drop')]:
            lat = attrs.get(f'{prefix}_lat')
            lng = attrs.get(f'{prefix}_lng')
            if lat is not None and lng is not None:
                if not (ERNAKULAM['min_lat'] <= lat <= ERNAKULAM['max_lat']
                        and ERNAKULAM['min_lng'] <= lng <= ERNAKULAM['max_lng']):
                    raise serializers.ValidationError({
                        f'{prefix}_lat': f'{label} coordinates must be within Ernakulam district '
                                         f'(lat {ERNAKULAM["min_lat"]}–{ERNAKULAM["max_lat"]}, '
                                         f'lng {ERNAKULAM["min_lng"]}–{ERNAKULAM["max_lng"]}).'
                    })

        # ── Time Restriction Check (at least 1 hour lead time) ──
        booking_date = attrs.get('date')
        booking_time = attrs.get('time')
        if booking_date and booking_time:
            from datetime import datetime, timedelta
            journey_dt = timezone.make_aware(datetime.combine(booking_date, booking_time))
            min_allowed_dt = timezone.now() + timedelta(hours=1)
            
            if journey_dt < min_allowed_dt:
                raise serializers.ValidationError(
                    {'time': 'Bookings must be made at least 1 hour before journey time.'}
                )

        return attrs


class BookingStatusSerializer(serializers.ModelSerializer):
    """
    Admin serializer for status updates with strict state-machine validation.
    Prevents invalid transitions even via direct API/Postman calls.
    """

    class Meta:
        model = Booking
        fields = ['status', 'notes', 'admin_note', 'rejection_reason', 'vehicle']

    def validate_status(self, value):
        allowed_values = ['pending', 'approved', 'driver_assigned', 'completed', 'rejected', 'cancelled']
        if value not in allowed_values:
            raise serializers.ValidationError(
                f"Status must be one of: {', '.join(allowed_values)}."
            )
        return value

    def validate(self, attrs):
        new_status = attrs.get('status')
        if new_status and self.instance:
            current = self.instance.status

            # Block all changes on finalized bookings
            if current in TERMINAL_STATES:
                raise serializers.ValidationError({
                    'status': f'This booking is {current} and cannot be modified further.'
                })

            # Validate state transition
            allowed_next = VALID_TRANSITIONS.get(current, [])
            if new_status not in allowed_next:
                raise serializers.ValidationError({
                    'status': f'Cannot transition from "{current}" to "{new_status}". '
                              f'Allowed transitions: {", ".join(allowed_next) if allowed_next else "none"}.'
                })

            # Rejection workflow check
            if new_status == 'rejected' and not attrs.get('rejection_reason'):
                raise serializers.ValidationError({'rejection_reason': 'Please provide a reason for rejection.'})

            # Vehicle and overlapping trip check
            vehicle = attrs.get('vehicle') or self.instance.vehicle
            if new_status in ['approved', 'driver_assigned']:
                if not vehicle:
                    raise serializers.ValidationError({'vehicle': 'A vehicle must be assigned to approve the booking.'})
                
                # Check overlaps
                from datetime import datetime, timedelta
                start_dt = timezone.make_aware(datetime.combine(self.instance.date, self.instance.time))
                end_dt = start_dt + timedelta(hours=self.instance.expected_duration_hours)
                
                overlapping = Booking.objects.filter(
                    vehicle=vehicle,
                    status__in=['approved', 'driver_assigned']
                ).exclude(pk=self.instance.pk)
                
                for b in overlapping:
                    b_start = timezone.make_aware(datetime.combine(b.date, b.time))
                    b_end = b_start + timedelta(hours=b.expected_duration_hours)
                    if max(start_dt, b_start) < min(end_dt, b_end):
                        raise serializers.ValidationError({
                            'vehicle': f'Vehicle "{vehicle.name}" is already booked for an overlapping trip '
                                       f'from {b.time.strftime("%I:%M %p")} to {b_end.time().strftime("%I:%M %p")} on {b.date}.'
                        })

        return attrs
