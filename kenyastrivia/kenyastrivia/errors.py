from rest_framework.exceptions import (
    APIException, AuthenticationFailed, NotAuthenticated, NotFound,
    PermissionDenied, Throttled, ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


class ApiError(APIException):
    """Raise this anywhere to return one of our error codes."""

    def __init__(self, code, message, status_code=400):
        super().__init__(detail=message, code=code)
        self.error_code = code
        self.status_code = status_code


def _body(code, message, **extra):
    return {"code": code, "message": message, **extra}


def api_exception_handler(exc, context):
    if isinstance(exc, ApiError):
        return Response(_body(exc.error_code, str(exc.detail)), status=exc.status_code)

    if isinstance(exc, (InvalidToken, TokenError)):
        text = str(getattr(exc, "detail", exc)).lower()
        code = "access_token_expired" if "expired" in text else "not_authenticated"
        return Response(_body(code, "Authentication failed."), status=401)

    if isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        return Response(_body("not_authenticated", "Authentication required."), status=401)

    if isinstance(exc, PermissionDenied):
        code = "guest_not_allowed" if exc.get_codes() == "guest_not_allowed" else "forbidden"
        return Response(_body(code, str(exc.detail)), status=403)

    if isinstance(exc, Throttled):
        return Response(_body("rate_limited", "Too many requests. Try again shortly."), status=429)

    if isinstance(exc, NotFound):
        return Response(_body("not_found", "Not found."), status=404)

    if isinstance(exc, ValidationError):
        return Response(_body("invalid_request", "The request data is not valid.", details=exc.detail), status=400)

    return drf_exception_handler(exc, context)