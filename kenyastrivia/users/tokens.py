from datetime import timedelta

from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from .models import GuestSession

GUEST_TOKEN_LIFETIME = timedelta(hours=24)


def tokens_for_user(user):
    """Access and refresh tokens for a signed-in account."""
    refresh = RefreshToken.for_user(user)
    refresh["kind"] = "user"
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def start_guest_session():
    """Create a guest session and a single 24-hour access token for it."""
    guest = GuestSession.objects.create()
    token = AccessToken()
    token["kind"] = "guest"
    token["guest_id"] = str(guest.id)
    token.set_exp(lifetime=GUEST_TOKEN_LIFETIME)
    return guest, str(token)