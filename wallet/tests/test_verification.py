import uuid
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

from wallet import services
from wallet.models import LedgerEntry

pytestmark = pytest.mark.django_db


def test_healthy_wallet_is_consistent(wallet, fund):
    fund(wallet, 500)
    services.debit(wallet.user, 200, uuid.uuid4())

    result = services.verify_wallet(wallet)

    assert result.consistent is True
    assert result.expected_balance == 300
    assert result.actual_balance == 300
    assert result.problems == ()


def test_tampered_balance_is_detected(wallet, fund):
    fund(wallet, 500)
    with connection.cursor() as cursor:
        cursor.execute("UPDATE wallet_wallet SET balance = %s WHERE id = %s", [999, wallet.pk])
    wallet.refresh_from_db()

    result = services.verify_wallet(wallet)

    assert result.consistent is False
    assert result.expected_balance == 500
    assert result.actual_balance == 999
    assert any("I1" in problem for problem in result.problems)


def test_broken_balance_after_chain_is_detected(wallet, fund):
    fund(wallet, 500)
    entry = LedgerEntry.objects.filter(wallet=wallet).first()
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE wallet_ledgerentry SET balance_after = %s WHERE id = %s",
            [123, entry.pk],
        )

    result = services.verify_wallet(wallet)

    assert result.consistent is False
    assert any(f"entry {entry.pk}" in problem for problem in result.problems)


def test_command_reports_a_healthy_wallet(wallet, fund):
    fund(wallet, 100)
    out = StringIO()

    call_command("verify_ledger", stdout=out)

    assert "consistent" in out.getvalue().lower()


def test_command_exits_non_zero_for_an_inconsistent_wallet(wallet, fund):
    fund(wallet, 100)
    with connection.cursor() as cursor:
        cursor.execute("UPDATE wallet_wallet SET balance = %s WHERE id = %s", [0, wallet.pk])

    with pytest.raises(CommandError):
        call_command("verify_ledger", stdout=StringIO(), stderr=StringIO())
