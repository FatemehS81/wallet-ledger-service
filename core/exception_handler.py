"""Single place that maps domain and DRF errors to the public error envelope."""

import logging

from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from accounts.exceptions import UsernameTaken
from wallet.exceptions import (
    AmountLimitExceeded,
    BalanceLimitExceeded,
    IdempotencyConflict,
    InsufficientFunds,
    InvalidAmount,
    InvalidIdempotencyKey,
    WalletNotFound,
)

logger = logging.getLogger(__name__)


def error_response(code: str, message: str, http_status: int, details=None) -> Response:
    return Response(
        {
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        },
        status=http_status,
    )


DOMAIN_ERRORS = {
    WalletNotFound: ("wallet_not_found", status.HTTP_404_NOT_FOUND),
    InvalidAmount: ("validation_error", status.HTTP_400_BAD_REQUEST),
    AmountLimitExceeded: ("amount_limit_exceeded", status.HTTP_400_BAD_REQUEST),
    InvalidIdempotencyKey: ("invalid_idempotency_key", status.HTTP_400_BAD_REQUEST),
    IdempotencyConflict: ("idempotency_conflict", status.HTTP_409_CONFLICT),
    InsufficientFunds: ("insufficient_funds", status.HTTP_422_UNPROCESSABLE_ENTITY),
    BalanceLimitExceeded: ("balance_limit_exceeded", status.HTTP_422_UNPROCESSABLE_ENTITY),
    UsernameTaken: ("username_taken", status.HTTP_400_BAD_REQUEST),
}


def wallet_exception_handler(exc, context):
    for error_class, (code, http_status) in DOMAIN_ERRORS.items():
        if isinstance(exc, error_class):
            return error_response(code, str(exc), http_status)

    if isinstance(exc, ValidationError):
        response = drf_exception_handler(exc, context)
        return error_response(
            "validation_error",
            "Invalid input.",
            response.status_code,
            details=response.data,
        )

    if isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        return error_response(
            "not_authenticated",
            "Authentication credentials were not provided or are invalid.",
            status.HTTP_401_UNAUTHORIZED,
        )

    response = drf_exception_handler(exc, context)
    if response is not None:
        code = getattr(exc, "default_code", "error")
        return error_response(code, str(exc), response.status_code, details=response.data)

    logger.exception("Unhandled exception in API request")
    return error_response(
        "internal_error",
        "An unexpected error occurred.",
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
