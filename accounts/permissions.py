from rest_framework.permissions import BasePermission


class IsAdminUser(BasePermission):
    """
    Custom permission that only allows access to users with is_admin=True.
    This is distinct from Django's built-in is_staff flag.
    """
    message = 'You must be an administrator to perform this action.'

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_admin
        )
