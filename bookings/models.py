from django.db import models
from django.conf import settings
import uuid

class Vehicle(models.Model):
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('maintenance', 'Maintenance'),
    ]
    name = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

class Booking(models.Model):
    """
    Core booking model. Linked to a User, stores all trip details
    and a lifecycle status (Pending → Approved / Rejected).
    """

    TRIP_TYPES = [
        ('airport_pickup', 'Airport Pickup'),
        ('airport_drop', 'Airport Drop'),
        ('tour_package', 'Tour Package'),
        ('taxi_booking', 'Taxi Booking'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('driver_assigned', 'Driver Assigned'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bookings',
        verbose_name='Customer',
    )
    public_id = models.UUIDField(
        default=uuid.uuid4, 
        editable=False, 
        unique=True,
        verbose_name='Public ID'
    )
    trip_type = models.CharField(
        max_length=20,
        choices=TRIP_TYPES,
        verbose_name='Trip Type',
    )
    name = models.CharField(max_length=150, verbose_name='Passenger Name')
    phone_number = models.CharField(max_length=20, verbose_name='Phone Number')
    num_people = models.PositiveIntegerField(verbose_name='Number of Passengers')
    from_location = models.CharField(max_length=200, verbose_name='Pickup Location')
    to_location = models.CharField(max_length=200, verbose_name='Drop Location')
    date = models.DateField(verbose_name='Travel Date')
    time = models.TimeField(verbose_name='Pickup Time')
    notes = models.TextField(blank=True, null=True, verbose_name='Additional Notes')

    # ── Map-based location fields ──
    pickup_address = models.CharField(
        max_length=500, blank=True, null=True,
        verbose_name='Pickup Address (Geocoded)',
    )
    pickup_lat = models.FloatField(blank=True, null=True, verbose_name='Pickup Latitude')
    pickup_lng = models.FloatField(blank=True, null=True, verbose_name='Pickup Longitude')
    drop_address = models.CharField(
        max_length=500, blank=True, null=True,
        verbose_name='Drop Address (Geocoded)',
    )
    drop_lat = models.FloatField(blank=True, null=True, verbose_name='Drop Latitude')
    drop_lng = models.FloatField(blank=True, null=True, verbose_name='Drop Longitude')

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        db_index=True,
        verbose_name='Booking Status',
    )
    admin_note = models.TextField(blank=True, null=True, verbose_name='Admin Note')
    rejection_reason = models.CharField(max_length=255, blank=True, null=True, verbose_name='Rejection Reason')
    vehicle = models.ForeignKey(
        Vehicle, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='bookings', verbose_name='Assigned Vehicle'
    )
    expected_duration_hours = models.PositiveIntegerField(default=4, verbose_name='Expected Duration (Hours)')
    cancelled_at = models.DateTimeField(blank=True, null=True, verbose_name='Cancelled At')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Booking'
        verbose_name_plural = 'Bookings'
        indexes = [
            models.Index(fields=['status', 'created_at'], name='idx_booking_status_created'),
            models.Index(fields=['user', '-created_at'], name='idx_booking_user_created'),
            models.Index(fields=['date'], name='idx_booking_date'),
            models.Index(fields=['vehicle', 'status'], name='idx_booking_vehicle_status'),
        ]

    def __str__(self):
        return (
            f'#{self.pk} | {self.user.email} | '
            f'{self.get_trip_type_display()} | '
            f'{self.date} | {self.get_status_display()}'
        )
