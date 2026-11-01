import uuid

import pytest
from django.contrib.auth import get_user_model

from wallet import services
from wallet.exceptions import IdempotencyConflict, InsufficientFunds
from wallet.fingerprint import make_fingerprint
from wallet.models import LedgerEntry, Wallet

pytestmark = pytest.mark.django_db

User = get_user_model()


def test_same_key_and_payload_creates_one_entry_and_replays(wallet):
    key = uuid.uuid4()

    first, created_first = services.credit(wallet.user, 500, key, "Top-up")
    second, created_second = services.credit(wallet.user, 500, key, "Top-up")

    wallet.refresh_from_db()
    assert created_first is True
    assert created_second is False
    assert second.pk == first.pk
    assert wallet.balance == 500
    assert LedgerEntry.objects.filter(wallet=wallet).count() == 1


def test_same_key_with_different_amount_conflicts(wallet):
    key = uuid.uuid4()
    services.credit(wallet.user, 500, key)

    with pytest.raises(IdempotencyConflict):
        services.credit(wallet.user, 600, key)

    wallet.refresh_from_db()
    assert wallet.balance == 500
    assert LedgerEntry.objects.filter(wallet=wallet).count() == 1


def test_same_key_with_different_type_conflicts(wallet, fund):
    fund(wallet, 500)
    key = uuid.uuid4()
    services.credit(wallet.user, 100, key)

    with pytest.raises(IdempotencyConflict):
        services.debit(wallet.user, 100, key)


def test_same_key_with_different_description_replays_original(wallet):
    key = uuid.uuid4()
    first, _ = services.credit(wallet.user, 500, key, "original note")

    second, created = services.credit(wallet.user, 500, key, "a different note")

    assert created is False
    assert second.pk == first.pk
    assert second.description == "original note"
    assert LedgerEntry.objects.filter(wallet=wallet).count() == 1


def test_retry_after_insufficient_funds_is_evaluated_again(wallet):
    debit_key = uuid.uuid4()

    with pytest.raises(InsufficientFunds):
        services.debit(wallet.user, 500, debit_key)

    services.credit(wallet.user, 500, uuid.uuid4(), "deposit")
    entry, created = services.debit(wallet.user, 500, debit_key)

    wallet.refresh_from_db()
    assert created is True
    assert entry.type == LedgerEntry.Type.DEBIT
    assert wallet.balance == 0
    assert LedgerEntry.objects.filter(wallet=wallet).count() == 2


def test_same_key_for_two_users_does_not_interfere(wallet, other_user):
    other_wallet = Wallet.objects.create(user=other_user)
    key = uuid.uuid4()

    first, created_first = services.credit(wallet.user, 100, key)
    second, created_second = services.credit(other_user, 100, key)

    assert created_first is True
    assert created_second is True
    assert first.pk != second.pk
    assert LedgerEntry.objects.filter(wallet=wallet).count() == 1
    assert LedgerEntry.objects.filter(wallet=other_wallet).count() == 1


def test_fingerprint_is_deterministic_and_ignores_nothing_relevant():
    first = make_fingerprint(LedgerEntry.Type.CREDIT, 500)
    second = make_fingerprint(LedgerEntry.Type.CREDIT, 500)

    assert first == second
    assert first != make_fingerprint(LedgerEntry.Type.CREDIT, 501)
    assert first != make_fingerprint(LedgerEntry.Type.DEBIT, 500)
    assert len(first) == 64
