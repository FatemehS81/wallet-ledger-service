"""Wallet business rules.

Everything that depends on state (the idempotency lookup, balance checks, the
ledger insert and the balance update) happens inside one transaction under a
per-wallet row lock. Serialising requests for one wallet solves concurrent
debits, concurrent retries and partial writes with one mechanism.
"""

import uuid

from django.conf import settings
from django.db import IntegrityError, transaction

from wallet.exceptions import (
    AmountLimitExceeded,
    BalanceLimitExceeded,
    IdempotencyConflict,
    InsufficientFunds,
    InvalidAmount,
    WalletNotFound,
)
from wallet.fingerprint import make_fingerprint
from wallet.models import LedgerEntry, Wallet


def validate_amount(amount: object) -> int:
    """Return ``amount`` as an int or raise ``InvalidAmount``.

    Booleans are rejected explicitly because ``bool`` is a subclass of ``int``.
    """
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise InvalidAmount("Amount must be a positive integer.")
    if amount > settings.MAX_TRANSACTION_AMOUNT:
        raise AmountLimitExceeded("Amount exceeds the maximum transaction amount.")
    return amount


def compute_new_balance(balance: int, entry_type: str, amount: int) -> int:
    """Apply ``amount`` to ``balance`` and enforce the balance invariants."""
    if entry_type == LedgerEntry.Type.CREDIT:
        new_balance = balance + amount
        if new_balance > settings.MAX_WALLET_BALANCE:
            raise BalanceLimitExceeded("Credit would exceed the maximum wallet balance.")
        return new_balance
    if entry_type == LedgerEntry.Type.DEBIT:
        if amount > balance:
            raise InsufficientFunds("Insufficient funds.")
        return balance - amount
    raise ValueError(f"Unknown ledger entry type: {entry_type!r}")


def _is_unique_violation(exc: IntegrityError) -> bool:
    return getattr(exc.__cause__, "sqlstate", None) == "23505"


def _replay(
    user,
    idempotency_key: uuid.UUID,
    fingerprint: str,
) -> tuple[LedgerEntry, bool]:
    existing = LedgerEntry.objects.filter(
        wallet__user=user,
        idempotency_key=idempotency_key,
    ).first()
    if existing is None:
        raise RuntimeError("Idempotency conflict could not be resolved.")
    if existing.request_fingerprint != fingerprint:
        raise IdempotencyConflict("Idempotency-Key was reused with a different request.")
    return existing, False


def apply_entry(
    user,
    entry_type: str,
    amount: int,
    idempotency_key: uuid.UUID,
    description: str = "",
) -> tuple[LedgerEntry, bool]:
    """Apply one credit or debit to ``user``'s wallet.

    Returns ``(entry, created)``. ``created`` is False for an idempotent replay.
    Raises ``WalletNotFound``, ``InvalidAmount``, ``AmountLimitExceeded``,
    ``InsufficientFunds``, ``BalanceLimitExceeded`` or ``IdempotencyConflict``.
    """
    validate_amount(amount)
    fingerprint = make_fingerprint(entry_type, amount)

    try:
        with transaction.atomic():
            try:
                wallet = Wallet.objects.select_for_update().get(user=user)
            except Wallet.DoesNotExist:
                raise WalletNotFound("The user has no wallet.") from None

            # The lookup must run inside the lock: two simultaneous retries
            # would otherwise both see no entry and both write.
            existing = LedgerEntry.objects.filter(
                wallet=wallet,
                idempotency_key=idempotency_key,
            ).first()
            if existing is not None:
                if existing.request_fingerprint != fingerprint:
                    raise IdempotencyConflict(
                        "Idempotency-Key was reused with a different request."
                    )
                return existing, False

            new_balance = compute_new_balance(wallet.balance, entry_type, amount)
            entry = LedgerEntry.objects.create(
                wallet=wallet,
                type=entry_type,
                amount=amount,
                balance_after=new_balance,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
                description=description,
            )
            wallet.balance = new_balance
            wallet.save(update_fields=["balance", "updated_at"])
            return entry, True
    except IntegrityError as exc:
        # Safety net: the unique constraint should never fire because the lock
        # serialises requests, but if it does, resolve it after the rollback.
        if not _is_unique_violation(exc):
            raise
        return _replay(user, idempotency_key, fingerprint)


def credit(
    user,
    amount: int,
    idempotency_key: uuid.UUID,
    description: str = "",
) -> tuple[LedgerEntry, bool]:
    """Increase the user's balance. Idempotent per ``idempotency_key``."""
    return apply_entry(user, LedgerEntry.Type.CREDIT, amount, idempotency_key, description)


def debit(
    user,
    amount: int,
    idempotency_key: uuid.UUID,
    description: str = "",
) -> tuple[LedgerEntry, bool]:
    """Decrease the user's balance. Idempotent per ``idempotency_key``."""
    return apply_entry(user, LedgerEntry.Type.DEBIT, amount, idempotency_key, description)
