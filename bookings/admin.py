from django.contrib import admin
from .models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'user', 'trip_type', 'name', 'phone_number', 'num_people',
        'from_location', 'to_location', 'date', 'time', 'status', 'created_at',
    ]
    list_filter = ['status', 'trip_type', 'date']
    search_fields = ['user__email', 'user__name', 'name', 'from_location', 'to_location']
    ordering = ['-created_at']
    list_editable = ['status']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'date'

    fieldsets = (
        ('Trip Details', {
            'fields': ('user', 'trip_type', 'name', 'phone_number', 'num_people', 'notes')
        }),
        ('Route', {
            'fields': ('from_location', 'to_location', 'date', 'time')
        }),
        ('Map Coordinates', {
            'fields': (
                'pickup_address', 'pickup_lat', 'pickup_lng',
                'drop_address', 'drop_lat', 'drop_lng',
            ),
            'classes': ('collapse',),
            'description': 'GPS coordinates and reverse-geocoded addresses from the map.'
        }),
        ('Status', {
            'fields': ('status',)
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')
