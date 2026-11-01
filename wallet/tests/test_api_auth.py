from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from accounts.services import register_user
from wallet.models import Wallet

pytestmark = pytest.mark.django_db

User = get_user_model()

USERNAME = "ali"
PASSWORD = "strong-password-123"


def register(client, username=USERNAME, password=PASSWORD):
    return client.post(
        "/api/v1/auth/register",
        {"username": username, "password": password},
        format="json",
    )


def login(client, username=USERNAME, password=PASSWORD):
    return client.post(
        "/api/v1/auth/login",
        {"username": username, "password": password},
        format="json",
    )


def test_register_creates_user_and_wallet():
    client = APIClient()

    response = register(client)

    assert response.status_code == 201
    user = User.objects.get(username=USERNAME)
    assert response.json() == {"id": user.pk, "username": USERNAME}
    assert user.check_password(PASSWORD)
    assert Wallet.objects.filter(user=user).exists()


def test_duplicate_username_returns_username_taken():
    client = APIClient()
    register(client)

    response = register(client)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "username_taken"


def test_weak_password_returns_validation_error():
    client = APIClient()

    response = register(client, username="weak-user", password="123")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
    assert not User.objects.filter(username="weak-user").exists()


def test_registration_rolls_back_the_user_when_wallet_creation_fails(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("wallet creation failed")

    monkeypatch.setattr(
        "accounts.services.Wallet",
        SimpleNamespace(objects=SimpleNamespace(create=boom)),
    )

    with pytest.raises(RuntimeError):
        register_user("atomic-user", PASSWORD)

    assert not User.objects.filter(username="atomic-user").exists()


def test_login_returns_tokens_and_the_access_token_works():
    client = APIClient()
    register(client)

    response = login(client)

    assert response.status_code == 200
    body = response.json()
    assert "access" in body
    assert "refresh" in body

    balance = client.get(
        "/api/v1/wallet/balance",
        HTTP_AUTHORIZATION=f"Bearer {body['access']}",
    )
    assert balance.status_code == 200
    assert balance.json()["balance"] == 0


def test_login_with_wrong_password_returns_401():
    client = APIClient()
    register(client)

    response = login(client, password="wrong-password-456")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_refresh_rotation_invalidates_the_old_refresh_token():
    client = APIClient()
    register(client)
    old_refresh = login(client).json()["refresh"]

    rotated = client.post("/api/v1/auth/refresh", {"refresh": old_refresh}, format="json")

    assert rotated.status_code == 200
    assert rotated.json()["refresh"] != old_refresh

    reused = client.post("/api/v1/auth/refresh", {"refresh": old_refresh}, format="json")
    assert reused.status_code == 401


def test_logout_blacklists_the_refresh_token():
    client = APIClient()
    register(client)
    tokens = login(client).json()

    logout = client.post(
        "/api/v1/auth/logout",
        {"refresh": tokens["refresh"]},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {tokens['access']}",
    )
    assert logout.status_code == 200

    refresh = client.post(
        "/api/v1/auth/refresh",
        {"refresh": tokens["refresh"]},
        format="json",
    )
    assert refresh.status_code == 401


def test_logout_requires_authentication():
    client = APIClient()
    register(client)
    refresh = login(client).json()["refresh"]

    response = client.post("/api/v1/auth/logout", {"refresh": refresh}, format="json")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_logout_with_an_invalid_token_returns_401():
    client = APIClient()
    register(client)
    access = login(client).json()["access"]

    response = client.post(
        "/api/v1/auth/logout",
        {"refresh": "not-a-real-token"},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {access}",
    )

    assert response.status_code == 401


def test_logout_without_a_refresh_token_returns_validation_error():
    client = APIClient()
    register(client)
    access = login(client).json()["access"]

    response = client.post(
        "/api/v1/auth/logout",
        {},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {access}",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"
