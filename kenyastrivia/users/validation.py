from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email

from kenyastrivia.errors import ApiError

from .models import User


def clean_email(value):
    value = (value or "").strip().lower()
    try:
        validate_email(value)
    except DjangoValidationError:
        raise ApiError("invalid_email", "Enter a valid email address.", 400)
    return value


def clean_username(value):
    value = (value or "").strip()
    if not value:
        raise ApiError("username_missing", "Choose a username.", 400)
    try:
        User._meta.get_field("username").run_validators(value)
    except DjangoValidationError:
        raise ApiError("invalid_username", "Use 3 to 20 letters, numbers or underscores.", 400)
    return value


def username_is_taken(value):
    return User.objects.filter(username__iexact=value).exists()


def email_is_registered(value):
    return User.objects.filter(email__iexact=value).exists()


def profile_data(user):
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "date_joined": user.date_joined,
    }