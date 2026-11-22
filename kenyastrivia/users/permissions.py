from rest_framework.permissions import BasePermission


class IsAccount(BasePermission):
    """Signed-in accounts only. Guests are refused."""

    message = "Sign in to use this."
    code = "guest_not_allowed"

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and not getattr(user, "is_guest", False))