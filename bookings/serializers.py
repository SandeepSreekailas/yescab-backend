from rest_framework import serializers
from django.utils import timezone
from .models import Booking
from accounts.serializers import UserSerializer


class BookingSerializer(serializers.ModelSerializer):
    """
    Full booking serializer. Includes display-friendly fields for trip type and status.
    User is set automatically from the request; read-only for API consumers.
    """
    user_info = UserSerializer(source='user', read_only=True)
    trip_type_display = serializers.CharField(source='get_trip_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

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
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'user', 'status', 'created_at', 'updated_at']

    def validate_num_people(self, value):
        if value < 1:
            raise serializers.ValidationError('At least 1 passenger is required.')
        if value > 50:
            raise serializers.ValidationError('Maximum 50 passengers per booking.')
        return value

    def validate_phone_number(self, value):
        import re
        cleaned = re.sub(r'[\s\-\(\)\+]', '', value)
        if not cleaned.isdigit() or not (7 <= len(cleaned) <= 15):
            raise serializers.ValidationError('Enter a valid phone number (7–15 digits).')
        return value

    def validate_date(self, value):
        today = timezone.now().date()
        if value < today:
            raise serializers.ValidationError('Travel date cannot be in the past.')
        return value

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

        return attrs


class BookingStatusSerializer(serializers.ModelSerializer):
    """
    Minimal serializer for admin: only exposes status and notes for PATCH updates.
    """

    class Meta:
        model = Booking
        fields = ['status', 'notes']

    def validate_status(self, value):
        if value not in ['pending', 'approved', 'rejected']:
            raise serializers.ValidationError(
                'Status must be one of: pending, approved, rejected.'
            )
        return value
