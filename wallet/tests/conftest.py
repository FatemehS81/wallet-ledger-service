import uuid

import pytest
from django.contrib.auth import get_user_model

from wallet import services
from wallet.models import Wallet

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="test-user", password="strong-password-123")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(username="other-user", password="strong-password-123")


@pytest.fixture
def wallet(user):
    return Wallet.objects.create(user=user)


@pytest.fixture
def fund():
    """Fund a wallet through the service so invariants hold in test data."""

    def _fund(wallet, amount):
        return services.credit(wallet.user, amount, uuid.uuid4(), "seed")

    return _fund
