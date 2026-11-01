"""Account business rules.

Registration creates the user and the wallet in one transaction, so a failure
to create either leaves no partial account behind.
"""

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from accounts.exceptions import UsernameTaken
from wallet.models import Wallet

User = get_user_model()


def register_user(username: str, password: str):
    """Create a user and their wallet atomically.

    Raises ``UsernameTaken`` when the username already exists.
    """
    with transaction.atomic():
        if User.objects.filter(username=username).exists():
            raise UsernameTaken("Username is already taken.")
        try:
            user = User.objects.create_user(username=username, password=password)
        except IntegrityError as exc:
            if getattr(exc.__cause__, "sqlstate", None) == "23505":
                raise UsernameTaken("Username is already taken.") from None
            raise
        Wallet.objects.create(user=user)
    return user
