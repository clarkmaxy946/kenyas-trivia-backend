from django.core.exceptions import ValidationError
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from .models import GuestSession


class GuestPrincipal:
    """Stands in for a user when the caller is a guest."""

    is_authenticated = True
    is_active = True
    is_guest = True

    def __init__(self, session):
        self.session = session

    @property
    def id(self):
        return self.session.id

    pk = id


class PlayerAuthentication(JWTAuthentication):
    """Accepts account tokens and guest tokens, and tells them apart."""

    def get_user(self, validated_token):
        if validated_token.get("kind") == "guest":
            try:
                session = GuestSession.objects.get(id=validated_token["guest_id"])
            except (GuestSession.DoesNotExist, ValidationError, KeyError):
                raise InvalidToken("Guest session not found")
            if session.is_expired():
                raise InvalidToken("Guest session expired")
            return GuestPrincipal(session)
        return super().get_user(validated_token)