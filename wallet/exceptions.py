"""Domain exceptions.

Services raise these exceptions. They contain no HTTP concepts; the API
exception handler is the only place that maps them to status codes.
"""


class WalletError(Exception):
    """Base class for wallet domain errors."""


class AppendOnlyViolation(WalletError):
    """Raised when code tries to modify or remove a ledger entry."""
