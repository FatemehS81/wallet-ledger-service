"""Concurrency tests against real PostgreSQL.

These tests need ``transaction=True`` because the normal pytest-django wrapper
would hide real row locking behind a single transaction. Threads start together
through a barrier, never through sleeps, and each thread closes its own database
connection when it finishes.
"""

import threading
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.db import connection

from wallet import services
from wallet.exceptions import InsufficientFunds
from wallet.models import LedgerEntry, Wallet

User = get_user_model()

pytestmark = pytest.mark.django_db(transaction=True)


def create_wallet(username: str):
    user = User.objects.create_user(username=username, password="strong-password-123")
    return user, Wallet.objects.create(user=user)


def run_concurrently(functions):
    barrier = threading.Barrier(len(functions))
    outcomes: list = []
    lock = threading.Lock()

    def runner(function):
        barrier.wait()
        try:
            outcome = ("ok", function())
        except Exception as exc:  # noqa: BLE001 - the helper records failures for assertions
            outcome = ("error", exc)
        finally:
            connection.close()
        with lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=runner, args=(fn,)) for fn in functions]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not any(thread.is_alive() for thread in threads), "a worker thread did not finish"
    return outcomes


def test_concurrent_debits_never_make_balance_negative():
    user, wallet = create_wallet("concurrent-debits")
    services.credit(user, 500, uuid.uuid4(), "seed")

    outcomes = run_concurrently(
        [lambda: services.debit(user, 100, uuid.uuid4()) for _ in range(10)]
    )

    successes = [outcome for outcome in outcomes if outcome[0] == "ok"]
    failures = [
        outcome
        for outcome in outcomes
        if outcome[0] == "error" and isinstance(outcome[1], InsufficientFunds)
    ]

    assert len(successes) == 5
    assert len(failures) == 5
    wallet.refresh_from_db()
    assert wallet.balance == 0

    entries = list(LedgerEntry.objects.filter(wallet=wallet).order_by("id"))
    assert len(entries) == 6
    assert all(entry.balance_after >= 0 for entry in entries)


def test_concurrent_retries_with_one_key_create_one_entry():
    user, wallet = create_wallet("concurrent-retries")
    key = uuid.uuid4()

    outcomes = run_concurrently([lambda: services.credit(user, 100, key) for _ in range(10)])

    assert all(outcome[0] == "ok" for outcome in outcomes)
    entries = list(LedgerEntry.objects.filter(wallet=wallet))
    assert len(entries) == 1
    wallet.refresh_from_db()
    assert wallet.balance == 100

    entry_ids = {outcome[1][0].pk for outcome in outcomes}
    assert entry_ids == {entries[0].pk}
    assert [outcome[1][1] for outcome in outcomes].count(True) == 1


def test_mixed_concurrent_operations_keep_ledger_consistent():
    user, wallet = create_wallet("concurrent-mixed")
    services.credit(user, 1000, uuid.uuid4(), "seed")

    operations = []
    for _ in range(5):
        operations.append(lambda: services.credit(user, 100, uuid.uuid4()))
        operations.append(lambda: services.debit(user, 50, uuid.uuid4()))

    outcomes = run_concurrently(operations)
    assert all(outcome[0] == "ok" for outcome in outcomes)

    wallet.refresh_from_db()
    entries = list(LedgerEntry.objects.filter(wallet=wallet).order_by("id"))

    credits = sum(entry.amount for entry in entries if entry.type == LedgerEntry.Type.CREDIT)
    debits = sum(entry.amount for entry in entries if entry.type == LedgerEntry.Type.DEBIT)
    assert wallet.balance == credits - debits
    assert wallet.balance == 1000 + 5 * 100 - 5 * 50

    previous = 0
    for entry in entries:
        if entry.type == LedgerEntry.Type.CREDIT:
            expected = previous + entry.amount
        else:
            expected = previous - entry.amount
        assert entry.balance_after == expected
        previous = expected
    assert previous == wallet.balance
