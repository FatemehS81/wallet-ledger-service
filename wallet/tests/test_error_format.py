import uuid

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def assert_error(response, status_code, code):
    assert response.status_code == status_code
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str)
    assert "details" in body["error"]


def test_validation_error_envelope(api_client):
    response = api_client.post(
        "/api/v1/wallet/credit",
        {"amount": "not-an-integer"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )

    assert_error(response, 400, "validation_error")
    assert "amount" in response.json()["error"]["details"]


def test_invalid_idempotency_key_envelope(api_client):
    response = api_client.post(
        "/api/v1/wallet/credit",
        {"amount": 100},
        format="json",
        HTTP_IDEMPOTENCY_KEY="nope",
    )

    assert_error(response, 400, "invalid_idempotency_key")


def test_not_authenticated_envelope():
    response = APIClient().get("/api/v1/wallet/balance")

    assert_error(response, 401, "not_authenticated")


def test_wallet_not_found_envelope(user):
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get("/api/v1/wallet/balance")

    assert_error(response, 404, "wallet_not_found")


def test_insufficient_funds_envelope(api_client):
    response = api_client.post(
        "/api/v1/wallet/debit",
        {"amount": 100},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )

    assert_error(response, 422, "insufficient_funds")


def test_amount_limit_exceeded_envelope(api_client, settings):
    settings.MAX_TRANSACTION_AMOUNT = 100

    response = api_client.post(
        "/api/v1/wallet/credit",
        {"amount": 101},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )

    assert_error(response, 400, "amount_limit_exceeded")


def test_balance_limit_exceeded_envelope(api_client, settings):
    settings.MAX_WALLET_BALANCE = 100

    response = api_client.post(
        "/api/v1/wallet/credit",
        {"amount": 101},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )

    assert_error(response, 422, "balance_limit_exceeded")


def test_idempotency_conflict_envelope(api_client):
    key = str(uuid.uuid4())
    api_client.post(
        "/api/v1/wallet/credit",
        {"amount": 100},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )

    response = api_client.post(
        "/api/v1/wallet/credit",
        {"amount": 200},
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )

    assert_error(response, 409, "idempotency_conflict")


def test_unexpected_error_does_not_leak_internals(api_client, wallet, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr("wallet.services.credit", boom)

    response = api_client.post(
        "/api/v1/wallet/credit",
        {"amount": 100},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )

    assert_error(response, 500, "internal_error")
    assert "secret internal detail" not in response.content.decode()
