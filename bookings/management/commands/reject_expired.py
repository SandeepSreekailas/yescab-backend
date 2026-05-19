from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from datetime import timedelta
import logging

from bookings.models import Booking
from bookings.views import dispatch_status_change_email

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Automatically rejects pending bookings that are older than 1 hour.'

    def handle(self, *args, **options):
        self.stdout.write("Starting auto-reject task...")
        
        threshold = timezone.now() - timedelta(hours=1)
        expired = Booking.objects.filter(status='pending', created_at__lt=threshold)
        
        count = 0
        if expired.exists():
            for b in expired:
                b.status = 'rejected'
                b.rejection_reason = 'No admin response within allowed time'
                b.save(update_fields=['status', 'rejection_reason', 'updated_at'])
                
                try:
                    dispatch_status_change_email(b)
                except Exception as e:
                    logger.error(f"Auto-reject email failed for #{b.id}: {e}")
                
                count += 1
                
        self.stdout.write(self.style.SUCCESS(f'Successfully auto-rejected {count} expired bookings.'))
