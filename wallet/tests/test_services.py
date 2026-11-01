import uuid

import pytest
from django.contrib.auth import get_user_model

from wallet import services
from wallet.exceptions import (
    AmountLimitExceeded,
    BalanceLimitExceeded,
    InsufficientFunds,
    InvalidAmount,
)
from wallet.models import LedgerEntry, Wallet

pytestmark = pytest.mark.django_db

User = get_user_model()


def test_credit_updates_balance_and_creates_entry(wallet):
    entry, created = services.credit(wallet.user, 500, uuid.uuid4(), "Top-up")
    wallet.refresh_from_db()

    assert created is True
    assert wallet.balance == 500
    assert entry.type == LedgerEntry.Type.CREDIT
    assert entry.amount == 500
    assert entry.balance_after == 500
    assert entry.description == "Top-up"
    assert LedgerEntry.objects.filter(wallet=wallet).count() == 1


def test_debit_updates_balance_and_creates_entry(wallet, fund):
    fund(wallet, 800)

    entry, created = services.debit(wallet.user, 300, uuid.uuid4(), "Withdraw")
    wallet.refresh_from_db()

    assert created is True
    assert wallet.balance == 500
    assert entry.type == LedgerEntry.Type.DEBIT
    assert entry.balance_after == 500


def test_debit_equal_to_balance_leaves_zero(wallet, fund):
    fund(wallet, 300)

    entry, _ = services.debit(wallet.user, 300, uuid.uuid4())
    wallet.refresh_from_db()

    assert wallet.balance == 0
    assert entry.balance_after == 0


def test_debit_above_balance_creates_no_entry(wallet, fund):
    fund(wallet, 100)

    with pytest.raises(InsufficientFunds):
        services.debit(wallet.user, 101, uuid.uuid4())

    wallet.refresh_from_db()
    assert wallet.balance == 100
    assert LedgerEntry.objects.filter(wallet=wallet).count() == 1


def test_credit_above_balance_cap_creates_no_entry(wallet, settings):
    settings.MAX_WALLET_BALANCE = 1000

    with pytest.raises(BalanceLimitExceeded):
        services.credit(wallet.user, 1001, uuid.uuid4())

    wallet.refresh_from_db()
    assert wallet.balance == 0
    assert LedgerEntry.objects.filter(wallet=wallet).count() == 0


def test_amount_above_transaction_cap_creates_no_entry(wallet, settings):
    settings.MAX_TRANSACTION_AMOUNT = 100

    with pytest.raises(AmountLimitExceeded):
        services.credit(wallet.user, 101, uuid.uuid4())

    wallet.refresh_from_db()
    assert wallet.balance == 0
    assert LedgerEntry.objects.filter(wallet=wallet).count() == 0


@pytest.mark.parametrize("amount", [0, -5, "10", 1.5, True, None])
def test_invalid_amount_is_rejected(wallet, amount):
    with pytest.raises(InvalidAmount):
        services.credit(wallet.user, amount, uuid.uuid4())

    assert LedgerEntry.objects.filter(wallet=wallet).count() == 0


def test_failure_after_entry_insert_rolls_everything_back(wallet, fund, monkeypatch):
    fund(wallet, 100)

    def boom(*args, **kwargs):
        raise RuntimeError("simulated failure after the ledger insert")

    monkeypatch.setattr(Wallet, "save", boom)

    with pytest.raises(RuntimeError):
        services.credit(wallet.user, 50, uuid.uuid4())

    wallet.refresh_from_db()
    assert wallet.balance == 100
    assert LedgerEntry.objects.filter(wallet=wallet).count() == 1
    assert not LedgerEntry.objects.filter(wallet=wallet, balance_after=150).exists()


def test_missing_wallet_raises_wallet_not_found(user):
    from wallet.exceptions import WalletNotFound

    with pytest.raises(WalletNotFound):
        services.credit(user, 100, uuid.uuid4())

    assert Wallet.objects.filter(user=user).count() == 0
