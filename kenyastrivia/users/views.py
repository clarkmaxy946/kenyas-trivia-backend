from django.contrib.auth.models import update_last_login
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from kenyastrivia.errors import ApiError
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .permissions import IsAccount

from .models import User
from .tokens import start_guest_session, tokens_for_user
from .validation import (
    clean_email, clean_username, email_is_registered, profile_data, username_is_taken,
)


class OpenView(APIView):
    """Endpoints anyone can call. A bad or expired token must not block them."""

    authentication_classes = []
    permission_classes = [AllowAny]


class UsernameAvailableView(OpenView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "username_check"

    def get(self, request):
        username = clean_username(request.query_params.get("username"))
        return Response({"available": not username_is_taken(username)})


class SignUpView(OpenView):
    def post(self, request):
        email = clean_email(request.data.get("email"))
        username = clean_username(request.data.get("username"))
        password = request.data.get("password") or ""

        if email_is_registered(email):
            raise ApiError("email_already_registered", "That email already has an account.", 409)
        if username_is_taken(username):
            raise ApiError("username_taken", "That username is taken.", 409)

        try:
            validate_password(password, user=User(email=email, username=username))
        except DjangoValidationError as e:
            raise ApiError("weak_password", " ".join(e.messages), 400)

        try:
            with transaction.atomic():
                user = User.objects.create_user(username=username, email=email, password=password)
        except IntegrityError:
            # Two sign-ups at the same moment: work out which rule lost.
            if email_is_registered(email):
                raise ApiError("email_already_registered", "That email already has an account.", 409)
            raise ApiError("username_taken", "That username is taken.", 409)

        return Response(
            {"user": profile_data(user), "tokens": tokens_for_user(user)},
            status=status.HTTP_201_CREATED,
        )


class LoginView(OpenView):
    def post(self, request):
        email = (request.data.get("email") or "").strip()
        password = request.data.get("password") or ""

        user = User.objects.filter(email__iexact=email).first()
        if user is None or not user.is_active or not user.check_password(password):
            raise ApiError("invalid_credentials", "Email or password is wrong.", 401)

        update_last_login(None, user)
        return Response({"user": profile_data(user), "tokens": tokens_for_user(user)})
class RefreshView(OpenView):
    def post(self, request):
        serializer = TokenRefreshSerializer(data={"refresh": request.data.get("refresh")})
        try:
            serializer.is_valid(raise_exception=True)
        except (TokenError, InvalidToken, serializers.ValidationError):
            raise ApiError("refresh_token_invalid", "Please sign in again.", 401)
        return Response(serializer.validated_data)


class LogoutView(OpenView):
    def post(self, request):
        token = request.data.get("refresh")
        if token:
            try:
                RefreshToken(token).blacklist()
            except TokenError:
                pass  # already invalid, which is the result we wanted
        return Response(status=status.HTTP_204_NO_CONTENT)


class GuestView(OpenView):
    def post(self, request):
        guest, access = start_guest_session()
        return Response(
            {
                "guest": {"id": str(guest.id), "expires_at": guest.expires_at},
                "tokens": {"access": access},
            },
            status=status.HTTP_201_CREATED,
        )


class ProfileView(APIView):
    permission_classes = [IsAccount]

    def get(self, request):
        return Response(profile_data(request.user))    