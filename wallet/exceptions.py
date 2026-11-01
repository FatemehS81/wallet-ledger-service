"""Domain exceptions.

Services raise these exceptions. They contain no HTTP concepts; the API
exception handler is the only place that maps them to status codes.
"""


class WalletError(Exception):
    """Base class for wallet domain errors."""


class AppendOnlyViolation(WalletError):
    """Raised when code tries to modify or remove a ledger entry."""


class WalletNotFound(WalletError):
    """The user has no wallet."""


class InvalidAmount(WalletError):
    """The amount is not a positive integer."""


class AmountLimitExceeded(WalletError):
    """The amount is above ``MAX_TRANSACTION_AMOUNT``."""


class InsufficientFunds(WalletError):
    """A debit is larger than the current balance."""


class BalanceLimitExceeded(WalletError):
    """A credit would push the balance above ``MAX_WALLET_BALANCE``."""


class IdempotencyConflict(WalletError):
    """The same key was used before with a different type or amount."""
