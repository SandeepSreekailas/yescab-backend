import logging

from rest_framework.views import exception_handler
from rest_framework.exceptions import Throttled

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Custom DRF exception handler.

    - Replaces Throttled (429) responses with user-friendly messages.
    - All other exceptions are handled by DRF's default handler.
    """
    response = exception_handler(exc, context)

    if response is not None and isinstance(exc, Throttled):
        # Log the real wait time for backend debugging
        view = context.get('view')
        view_name = view.__class__.__name__ if view else 'Unknown'
        logger.warning(
            f'Throttled: {view_name} — retry in {exc.wait:.0f}s'
            if exc.wait else f'Throttled: {view_name}'
        )

        # Return clean, user-friendly message (hide internal timing)
        response.data = {'detail': 'Too many attempts. Please try again later.'}

    return response
