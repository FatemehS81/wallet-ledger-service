import uuid
from urllib.parse import urlparse

import pytest
from rest_framework.test import APIClient

from wallet import services
from wallet.models import LedgerEntry, Wallet

pytestmark = pytest.mark.django_db


def post_credit(client, amount, key=None, description=None):
    payload = {"amount": amount}
    if description is not None:
        payload["description"] = description
    extra = {}
    if key is not None:
        extra["HTTP_IDEMPOTENCY_KEY"] = key
    return client.post("/api/v1/wallet/credit", payload, format="json", **extra)


def test_credit_returns_201_and_the_new_entry(api_client, wallet):
    response = post_credit(api_client, 500, str(uuid.uuid4()), "Top-up")

    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "CREDIT"
    assert body["amount"] == 500
    assert body["balance_after"] == 500
    assert body["description"] == "Top-up"
    assert {"id", "type", "amount", "balance_after", "description", "created_at"} == set(body)
    wallet.refresh_from_db()
    assert wallet.balance == 500


def test_replay_returns_200_with_the_original_body(api_client, wallet):
    key = str(uuid.uuid4())
    first = post_credit(api_client, 500, key, "Top-up")
    second = post_credit(api_client, 500, key, "Top-up")

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json() == first.json()
    assert LedgerEntry.objects.filter(wallet=wallet).count() == 1


def test_missing_idempotency_key_returns_400(api_client):
    response = post_credit(api_client, 500)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_idempotency_key"


def test_malformed_idempotency_key_returns_400(api_client):
    response = post_credit(api_client, 500, "not-a-uuid")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_idempotency_key"


@pytest.mark.parametrize("amount", [0, -1, "100", 1.5, True, None])
def test_invalid_amounts_return_validation_error(api_client, amount):
    response = post_credit(api_client, amount, str(uuid.uuid4()))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_missing_amount_returns_validation_error(api_client):
    response = api_client.post(
        "/api/v1/wallet/credit",
        {},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_insufficient_funds_returns_422(api_client):
    response = api_client.post(
        "/api/v1/wallet/debit",
        {"amount": 100},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "insufficient_funds"


def test_balance_returns_the_current_balance(api_client, wallet):
    services.credit(wallet.user, 1500, uuid.uuid4())

    response = api_client.get("/api/v1/wallet/balance")

    assert response.status_code == 200
    assert response.json()["balance"] == 1500
    assert "updated_at" in response.json()


def test_user_cannot_see_another_users_balance_or_history(api_client, wallet, other_user):
    other_wallet = Wallet.objects.create(user=other_user)
    services.credit(other_user, 900, uuid.uuid4(), "not yours")

    balance = api_client.get("/api/v1/wallet/balance")
    history = api_client.get("/api/v1/wallet/transactions")

    assert balance.json()["balance"] == 0
    assert history.json()["results"] == []
    assert LedgerEntry.objects.filter(wallet=other_wallet).count() == 1


def test_history_is_ordered_newest_first(api_client, wallet, fund):
    fund(wallet, 100)
    services.credit(wallet.user, 200, uuid.uuid4())
    services.debit(wallet.user, 50, uuid.uuid4())

    response = api_client.get("/api/v1/wallet/transactions")

    ids = [entry["id"] for entry in response.json()["results"]]
    assert ids == sorted(ids, reverse=True)


def test_cursor_pagination_has_no_duplicates_or_gaps(api_client, wallet):
    for amount in range(1, 6):
        services.credit(wallet.user, amount, uuid.uuid4())

    expected_ids = list(
        LedgerEntry.objects.filter(wallet=wallet).order_by("-id").values_list("id", flat=True)
    )
    collected = []
    url = "/api/v1/wallet/transactions?limit=2"
    while url:
        response = api_client.get(url)
        body = response.json()
        collected.extend(entry["id"] for entry in body["results"])
        next_url = body["next"]
        if next_url:
            parsed = urlparse(next_url)
            url = f"{parsed.path}?{parsed.query}"
        else:
            url = None

    assert collected == expected_ids
    assert len(collected) == len(set(collected))


def test_type_filter_only_returns_matching_entries(api_client, wallet, fund):
    fund(wallet, 100)
    services.debit(wallet.user, 50, uuid.uuid4())

    response = api_client.get("/api/v1/wallet/transactions?type=DEBIT")

    results = response.json()["results"]
    assert results
    assert all(entry["type"] == "DEBIT" for entry in results)


def test_invalid_type_filter_returns_validation_error(api_client, wallet):
    response = api_client.get("/api/v1/wallet/transactions?type=NOPE")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_limit_is_capped_at_one_hundred(api_client, wallet):
    for amount in range(1, 106):
        services.credit(wallet.user, amount, uuid.uuid4())

    response = api_client.get("/api/v1/wallet/transactions?limit=1000")

    body = response.json()
    assert len(body["results"]) == 100
    assert body["next"] is not None


def test_wallet_not_found_returns_404(user):
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.get("/api/v1/wallet/balance")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "wallet_not_found"


def test_missing_token_returns_401():
    response = APIClient().get("/api/v1/wallet/balance")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"
