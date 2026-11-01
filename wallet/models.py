from django.conf import settings
from django.db import models

from wallet.exceptions import AppendOnlyViolation


class Wallet(models.Model):
    """A user's wallet.

    ``balance`` is a denormalised copy of the ledger sum. It is updated in the
    same transaction as the ledger entry that changes it and is guarded by a
    database CHECK constraint.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="wallet",
    )
    balance = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(balance__gte=0),
                name="wallet_balance_non_negative",
            ),
        ]

    def __str__(self) -> str:
        return f"Wallet(user_id={self.user_id}, balance={self.balance})"


class AppendOnlyQuerySet(models.QuerySet):
    """Blocks bulk mutations so history can never be rewritten."""

    def update(self, **kwargs):
        raise AppendOnlyViolation("Ledger entries are append-only and cannot be updated.")

    def delete(self):
        raise AppendOnlyViolation("Ledger entries are append-only and cannot be deleted.")


class LedgerEntry(models.Model):
    """One immutable balance change.

    Every successful credit or debit inserts exactly one row. Corrections are
    made with compensating entries, never by editing or deleting history.
    """

    class Type(models.TextChoices):
        CREDIT = "CREDIT", "Credit"
        DEBIT = "DEBIT", "Debit"

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.PROTECT,
        related_name="entries",
    )
    type = models.CharField(max_length=6, choices=Type.choices)
    amount = models.PositiveBigIntegerField()
    balance_after = models.PositiveBigIntegerField()
    idempotency_key = models.UUIDField()
    request_fingerprint = models.CharField(max_length=64)
    description = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="ledger_amount_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(balance_after__gte=0),
                name="ledger_balance_after_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(type__in=["CREDIT", "DEBIT"]),
                name="ledger_type_valid",
            ),
            models.UniqueConstraint(
                fields=["wallet", "idempotency_key"],
                name="ledger_unique_wallet_idempotency_key",
            ),
        ]
        indexes = [
            models.Index(fields=["wallet", "id"], name="ledger_wallet_id_idx"),
        ]
        ordering = ["-id"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AppendOnlyViolation("Ledger entries are append-only and cannot be modified.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyViolation("Ledger entries are append-only and cannot be deleted.")

    def __str__(self) -> str:
        return f"{self.type} {self.amount} (wallet_id={self.wallet_id})"
