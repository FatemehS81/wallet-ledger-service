import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APIClient

from wallet import docs_examples as examples

pytestmark = pytest.mark.django_db

User = get_user_model()
PASSWORD = "strong-password-123"


def has_examples(node) -> bool:
    if isinstance(node, dict):
        if node.get("examples"):
            return True
        return any(has_examples(value) for value in node.values())
    if isinstance(node, list):
        return any(has_examples(value) for value in node)
    return False


def register(client, username="ali"):
    return client.post(
        "/api/v1/auth/register",
        {"username": username, "password": PASSWORD},
        format="json",
    )


def make_authenticated_client(username="ali"):
    client = APIClient()
    register(client, username)
    tokens = client.post(
        "/api/v1/auth/login",
        {"username": username, "password": PASSWORD},
        format="json",
    ).json()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    return client, tokens


def test_schema_endpoint_returns_200():
    response = APIClient().get("/api/schema/")

    assert response.status_code == 200


def test_schema_validates_without_warnings():
    call_command("spectacular", "--validate", "--fail-on-warn", "--file", "/dev/null")


def test_every_operation_has_at_least_one_example():
    schema = APIClient().get("/api/schema/", HTTP_ACCEPT="application/json").json()

    for path, operations in schema["paths"].items():
        for method, operation in operations.items():
            assert has_examples(operation), f"{method.upper()} {path} has no documented example"


def test_register_example_matches_behaviour():
    response = APIClient().post(
        "/api/v1/auth/register",
        examples.REGISTER_REQUEST_EXAMPLE,
        format="json",
    )

    assert response.status_code == 201
    assert set(response.json()) == set(examples.REGISTER_RESPONSE_EXAMPLE)


def test_login_example_matches_behaviour():
    client = APIClient()
    register(client)

    response = client.post(
        "/api/v1/auth/login",
        examples.LOGIN_REQUEST_EXAMPLE,
        format="json",
    )

    assert response.status_code == 200
    assert set(response.json()) == set(examples.TOKEN_RESPONSE_EXAMPLE)


def test_credit_example_and_replay_match_behaviour():
    client, _ = make_authenticated_client()

    first = client.post(
        "/api/v1/wallet/credit",
        examples.CREDIT_REQUEST_EXAMPLE,
        format="json",
        HTTP_IDEMPOTENCY_KEY=examples.CREDIT_IDEMPOTENCY_KEY,
    )
    second = client.post(
        "/api/v1/wallet/credit",
        examples.CREDIT_REQUEST_EXAMPLE,
        format="json",
        HTTP_IDEMPOTENCY_KEY=examples.CREDIT_IDEMPOTENCY_KEY,
    )

    assert first.status_code == 201
    assert set(first.json()) == set(examples.CREDIT_RESPONSE_EXAMPLE)
    assert second.status_code == 200
    assert second.json() == first.json()


def test_debit_example_matches_behaviour():
    client, _ = make_authenticated_client()
    client.post(
        "/api/v1/wallet/credit",
        {"amount": 500},
        format="json",
        HTTP_IDEMPOTENCY_KEY=examples.CREDIT_IDEMPOTENCY_KEY,
    )

    response = client.post(
        "/api/v1/wallet/debit",
        examples.DEBIT_REQUEST_EXAMPLE,
        format="json",
        HTTP_IDEMPOTENCY_KEY=examples.DEBIT_IDEMPOTENCY_KEY,
    )

    assert response.status_code == 201
    assert set(response.json()) == set(examples.DEBIT_RESPONSE_EXAMPLE)
    assert response.json()["type"] == "DEBIT"
    assert response.json()["balance_after"] == 300


def test_balance_example_matches_behaviour():
    client, _ = make_authenticated_client()
    client.post(
        "/api/v1/wallet/credit",
        {"amount": 500},
        format="json",
        HTTP_IDEMPOTENCY_KEY=examples.CREDIT_IDEMPOTENCY_KEY,
    )

    response = client.get("/api/v1/wallet/balance")

    assert response.status_code == 200
    assert set(response.json()) == set(examples.BALANCE_RESPONSE_EXAMPLE)
    assert response.json()["balance"] == 500


def test_transactions_example_matches_behaviour():
    client, _ = make_authenticated_client()
    client.post(
        "/api/v1/wallet/credit",
        {"amount": 500},
        format="json",
        HTTP_IDEMPOTENCY_KEY=examples.CREDIT_IDEMPOTENCY_KEY,
    )

    response = client.get("/api/v1/wallet/transactions")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == set(examples.TRANSACTIONS_RESPONSE_EXAMPLE)
    assert set(body["results"][0]) == set(examples.CREDIT_RESPONSE_EXAMPLE)


def test_documented_validation_error_matches_behaviour():
    client, _ = make_authenticated_client()

    response = client.post(
        "/api/v1/wallet/credit",
        {"amount": "not-an-integer"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=examples.CREDIT_IDEMPOTENCY_KEY,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_documented_invalid_idempotency_key_matches_behaviour():
    client, _ = make_authenticated_client()

    response = client.post(
        "/api/v1/wallet/credit",
        examples.CREDIT_REQUEST_EXAMPLE,
        format="json",
        HTTP_IDEMPOTENCY_KEY="not-a-uuid",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_idempotency_key"


def test_documented_amount_limit_error_matches_behaviour(settings):
    settings.MAX_TRANSACTION_AMOUNT = 100
    client, _ = make_authenticated_client()

    response = client.post(
        "/api/v1/wallet/credit",
        examples.CREDIT_REQUEST_EXAMPLE,
        format="json",
        HTTP_IDEMPOTENCY_KEY=examples.CREDIT_IDEMPOTENCY_KEY,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "amount_limit_exceeded"


def test_documented_unauthenticated_error_matches_behaviour():
    response = APIClient().post(
        "/api/v1/wallet/credit",
        examples.CREDIT_REQUEST_EXAMPLE,
        format="json",
        HTTP_IDEMPOTENCY_KEY=examples.CREDIT_IDEMPOTENCY_KEY,
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_documented_wallet_not_found_error_matches_behaviour():
    user = User.objects.create_user(username="no-wallet", password=PASSWORD)
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get("/api/v1/wallet/balance")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "wallet_not_found"


def test_documented_idempotency_conflict_matches_behaviour():
    client, _ = make_authenticated_client()
    key = examples.CREDIT_IDEMPOTENCY_KEY
    client.post(
        "/api/v1/wallet/credit",
        {"amount": 500},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )

    response = client.post(
        "/api/v1/wallet/credit",
        {"amount": 600},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "idempotency_conflict"


def test_documented_balance_limit_error_matches_behaviour(settings):
    settings.MAX_WALLET_BALANCE = 100
    client, _ = make_authenticated_client()

    response = client.post(
        "/api/v1/wallet/credit",
        examples.CREDIT_REQUEST_EXAMPLE,
        format="json",
        HTTP_IDEMPOTENCY_KEY=examples.CREDIT_IDEMPOTENCY_KEY,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "balance_limit_exceeded"


def test_documented_insufficient_funds_error_matches_behaviour():
    client, _ = make_authenticated_client()

    response = client.post(
        "/api/v1/wallet/debit",
        examples.DEBIT_REQUEST_EXAMPLE,
        format="json",
        HTTP_IDEMPOTENCY_KEY=examples.DEBIT_IDEMPOTENCY_KEY,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "insufficient_funds"


def test_documented_username_taken_error_matches_behaviour():
    client = APIClient()
    register(client)

    response = client.post(
        "/api/v1/auth/register",
        examples.REGISTER_REQUEST_EXAMPLE,
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "username_taken"


def test_documented_weak_password_error_matches_behaviour():
    response = APIClient().post(
        "/api/v1/auth/register",
        {"username": "weak", "password": "123"},
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_documented_login_failure_matches_behaviour():
    client = APIClient()
    register(client)

    response = client.post(
        "/api/v1/auth/login",
        {"username": "ali", "password": "wrong-password-456"},
        format="json",
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_documented_refresh_example_matches_behaviour():
    client = APIClient()
    register(client)
    refresh = client.post(
        "/api/v1/auth/login",
        {"username": "ali", "password": PASSWORD},
        format="json",
    ).json()["refresh"]

    response = client.post("/api/v1/auth/refresh", {"refresh": refresh}, format="json")

    assert response.status_code == 200
    assert set(response.json()) == set(examples.TOKEN_RESPONSE_EXAMPLE)


def test_documented_invalid_refresh_matches_behaviour():
    response = APIClient().post(
        "/api/v1/auth/refresh",
        examples.REFRESH_REQUEST_EXAMPLE,
        format="json",
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_documented_logout_example_matches_behaviour():
    client, tokens = make_authenticated_client()

    response = client.post(
        "/api/v1/auth/logout",
        {"refresh": tokens["refresh"]},
        format="json",
    )

    assert response.status_code == 200


def test_swagger_ui_returns_200():
    response = APIClient().get("/api/docs/")

    assert response.status_code == 200
