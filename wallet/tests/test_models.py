import uuid

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.db.models import ProtectedError

from wallet.exceptions import AppendOnlyViolation
from wallet.models import LedgerEntry, Wallet

User = get_user_model()


@pytest.fixture
def wallet(db):
    user = User.objects.create_user(username="model-user", password="strong-password-123")
    return Wallet.objects.create(user=user)


def make_entry(wallet, **overrides):
    defaults = {
        "wallet": wallet,
        "type": LedgerEntry.Type.CREDIT,
        "amount": 100,
        "balance_after": 100,
        "idempotency_key": uuid.uuid4(),
        "request_fingerprint": "a" * 64,
        "description": "",
    }
    defaults.update(overrides)
    return LedgerEntry.objects.create(**defaults)


@pytest.mark.django_db
def test_zero_amount_is_rejected_by_the_database(wallet):
    with pytest.raises(IntegrityError):
        make_entry(wallet, amount=0)


@pytest.mark.django_db
def test_negative_balance_is_rejected_by_the_database():
    user = User.objects.create_user(username="negative-balance", password="strong-password-123")

    with pytest.raises(IntegrityError):
        Wallet.objects.create(user=user, balance=-1)


@pytest.mark.django_db
def test_duplicate_idempotency_key_per_wallet_is_rejected(wallet):
    key = uuid.uuid4()
    make_entry(wallet, idempotency_key=key)

    with pytest.raises(IntegrityError):
        make_entry(wallet, idempotency_key=key)


@pytest.mark.django_db
def test_saving_an_existing_entry_is_blocked(wallet):
    entry = make_entry(wallet)
    entry.amount = 200

    with pytest.raises(AppendOnlyViolation):
        entry.save()


@pytest.mark.django_db
def test_deleting_an_entry_is_blocked(wallet):
    entry = make_entry(wallet)

    with pytest.raises(AppendOnlyViolation):
        entry.delete()


@pytest.mark.django_db
def test_queryset_update_is_blocked(wallet):
    make_entry(wallet)

    with pytest.raises(AppendOnlyViolation):
        LedgerEntry.objects.filter(wallet=wallet).update(amount=999)


@pytest.mark.django_db
def test_queryset_delete_is_blocked(wallet):
    make_entry(wallet)

    with pytest.raises(AppendOnlyViolation):
        LedgerEntry.objects.filter(wallet=wallet).delete()


@pytest.mark.django_db
def test_deleting_a_wallet_with_entries_is_blocked(wallet):
    make_entry(wallet)

    with pytest.raises(ProtectedError):
        wallet.delete()
