from django.urls import path
from .views import (
    BookingListCreateView,
    BookingDetailView,
    AdminBookingListView,
    AdminBookingStatusView,
    BookingCancelView,
    VehicleListView,
    AdminStatsView,
    UserStatsView,
)

urlpatterns = [
    # User endpoints
    path('', BookingListCreateView.as_view(), name='booking_list_create'),
    path('stats/', UserStatsView.as_view(), name='user_stats'),
    path('<uuid:public_id>/', BookingDetailView.as_view(), name='booking_detail'),
    path('<uuid:public_id>/cancel/', BookingCancelView.as_view(), name='booking_cancel'),

    # Admin endpoints
    path('admin/stats/', AdminStatsView.as_view(), name='admin_stats'),
    path('admin/all/', AdminBookingListView.as_view(), name='admin_booking_list'),
    path('admin/vehicles/', VehicleListView.as_view(), name='admin_vehicle_list'),
    path('admin/<uuid:public_id>/status/', AdminBookingStatusView.as_view(), name='admin_booking_status'),
]
