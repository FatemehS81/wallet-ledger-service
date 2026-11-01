"""Example payloads shared by the OpenAPI schema and the documentation tests.

Keeping every example in one module means the tests can execute the same
payloads the schema advertises, so the documentation cannot silently drift
from the API's behaviour.
"""

from drf_spectacular.utils import OpenApiExample

CREDIT_IDEMPOTENCY_KEY = "3b241101-e2bb-4255-8caf-4136c566a962"
DEBIT_IDEMPOTENCY_KEY = "7c9e6679-7425-40de-944b-e07fc1f90ae7"

REGISTER_REQUEST_EXAMPLE = {"username": "ali", "password": "strong-password-123"}
LOGIN_REQUEST_EXAMPLE = {"username": "ali", "password": "strong-password-123"}
REFRESH_REQUEST_EXAMPLE = {"refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.example"}
LOGOUT_REQUEST_EXAMPLE = {"refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.example"}

CREDIT_REQUEST_EXAMPLE = {"amount": 500, "description": "Top-up"}
DEBIT_REQUEST_EXAMPLE = {"amount": 200, "description": "Withdrawal"}

REGISTER_RESPONSE_EXAMPLE = {"id": 1, "username": "ali"}
TOKEN_RESPONSE_EXAMPLE = {
    "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.access",
    "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.refresh",
}
CREDIT_RESPONSE_EXAMPLE = {
    "id": 42,
    "type": "CREDIT",
    "amount": 500,
    "balance_after": 1500,
    "description": "Top-up",
    "created_at": "2026-11-01T10:00:00Z",
}
DEBIT_RESPONSE_EXAMPLE = {
    "id": 43,
    "type": "DEBIT",
    "amount": 200,
    "balance_after": 1300,
    "description": "Withdrawal",
    "created_at": "2026-11-01T10:05:00Z",
}
BALANCE_RESPONSE_EXAMPLE = {"balance": 1500, "updated_at": "2026-11-01T10:00:00Z"}
TRANSACTIONS_RESPONSE_EXAMPLE = {
    "next": "http://testserver/api/v1/wallet/transactions?cursor=cD0xNQ&limit=20",
    "previous": None,
    "results": [CREDIT_RESPONSE_EXAMPLE, DEBIT_RESPONSE_EXAMPLE],
}


def error_example(name: str, code: str, message: str, details=None) -> OpenApiExample:
    return OpenApiExample(
        name=name,
        value={"error": {"code": code, "message": message, "details": details or {}}},
        response_only=True,
    )


VALIDATION_ERROR_EXAMPLE = error_example(
    "Validation error",
    "validation_error",
    "Invalid input.",
    {"amount": ["A valid integer is required."]},
)
INVALID_IDEMPOTENCY_KEY_EXAMPLE = error_example(
    "Invalid idempotency key",
    "invalid_idempotency_key",
    "Idempotency-Key must be a valid UUID.",
)
AMOUNT_LIMIT_EXCEEDED_EXAMPLE = error_example(
    "Amount limit exceeded",
    "amount_limit_exceeded",
    "Amount exceeds the maximum transaction amount.",
)
NOT_AUTHENTICATED_EXAMPLE = error_example(
    "Not authenticated",
    "not_authenticated",
    "Authentication credentials were not provided or are invalid.",
)
WALLET_NOT_FOUND_EXAMPLE = error_example(
    "Wallet not found",
    "wallet_not_found",
    "The user has no wallet.",
)
IDEMPOTENCY_CONFLICT_EXAMPLE = error_example(
    "Idempotency conflict",
    "idempotency_conflict",
    "Idempotency-Key was reused with a different request.",
)
INSUFFICIENT_FUNDS_EXAMPLE = error_example(
    "Insufficient funds",
    "insufficient_funds",
    "Insufficient funds.",
)
BALANCE_LIMIT_EXCEEDED_EXAMPLE = error_example(
    "Balance limit exceeded",
    "balance_limit_exceeded",
    "Credit would exceed the maximum wallet balance.",
)
USERNAME_TAKEN_EXAMPLE = error_example(
    "Username taken",
    "username_taken",
    "Username is already taken.",
)

REGISTER_REQUEST_EXAMPLES = [
    OpenApiExample(
        "Registration request",
        value=REGISTER_REQUEST_EXAMPLE,
        request_only=True,
    )
]
REGISTER_RESPONSE_EXAMPLES = [
    OpenApiExample(
        "Registered user",
        value=REGISTER_RESPONSE_EXAMPLE,
        response_only=True,
    )
]
LOGIN_REQUEST_EXAMPLES = [
    OpenApiExample("Login request", value=LOGIN_REQUEST_EXAMPLE, request_only=True)
]
LOGIN_RESPONSE_EXAMPLES = [
    OpenApiExample("Token pair", value=TOKEN_RESPONSE_EXAMPLE, response_only=True)
]
REFRESH_REQUEST_EXAMPLES = [
    OpenApiExample("Refresh request", value=REFRESH_REQUEST_EXAMPLE, request_only=True)
]
REFRESH_RESPONSE_EXAMPLES = [
    OpenApiExample("Rotated token pair", value=TOKEN_RESPONSE_EXAMPLE, response_only=True)
]
LOGOUT_REQUEST_EXAMPLES = [
    OpenApiExample("Logout request", value=LOGOUT_REQUEST_EXAMPLE, request_only=True)
]

CREDIT_REQUEST_EXAMPLES = [
    OpenApiExample("Credit request", value=CREDIT_REQUEST_EXAMPLE, request_only=True)
]
CREDIT_CREATED_EXAMPLES = [
    OpenApiExample("New credit entry", value=CREDIT_RESPONSE_EXAMPLE, response_only=True)
]
CREDIT_REPLAY_EXAMPLES = [
    OpenApiExample("Idempotent replay", value=CREDIT_RESPONSE_EXAMPLE, response_only=True)
]
DEBIT_REQUEST_EXAMPLES = [
    OpenApiExample("Debit request", value=DEBIT_REQUEST_EXAMPLE, request_only=True)
]
DEBIT_CREATED_EXAMPLES = [
    OpenApiExample("New debit entry", value=DEBIT_RESPONSE_EXAMPLE, response_only=True)
]
DEBIT_REPLAY_EXAMPLES = [
    OpenApiExample("Idempotent replay", value=DEBIT_RESPONSE_EXAMPLE, response_only=True)
]
BALANCE_RESPONSE_EXAMPLES = [
    OpenApiExample("Current balance", value=BALANCE_RESPONSE_EXAMPLE, response_only=True)
]
TRANSACTIONS_RESPONSE_EXAMPLES = [
    OpenApiExample(
        "First page of history",
        value=TRANSACTIONS_RESPONSE_EXAMPLE,
        response_only=True,
    )
]

AUTH_ERROR_EXAMPLES = [NOT_AUTHENTICATED_EXAMPLE]
WALLET_NOT_FOUND_EXAMPLES = [WALLET_NOT_FOUND_EXAMPLE]
