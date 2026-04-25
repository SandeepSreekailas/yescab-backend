from django.urls import path
from .views import (
    BookingListCreateView,
    BookingDetailView,
    AdminBookingListView,
    AdminBookingStatusView,
)

urlpatterns = [
    # User endpoints
    path('', BookingListCreateView.as_view(), name='booking_list_create'),
    path('<int:pk>/', BookingDetailView.as_view(), name='booking_detail'),

    # Admin endpoints
    path('admin/all/', AdminBookingListView.as_view(), name='admin_booking_list'),
    path('admin/<int:pk>/status/', AdminBookingStatusView.as_view(), name='admin_booking_status'),
]
