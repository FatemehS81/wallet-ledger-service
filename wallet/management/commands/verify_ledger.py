from django.core.management.base import BaseCommand, CommandError

from wallet.models import Wallet
from wallet.services import verify_wallet


class Command(BaseCommand):
    help = "Verify every wallet balance against its ledger and report inconsistencies."

    def handle(self, *args, **options):
        wallets = Wallet.objects.all().order_by("pk")
        total = wallets.count()
        inconsistent = 0

        for wallet in wallets:
            result = verify_wallet(wallet)
            if result.consistent:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"wallet {wallet.pk}: consistent (balance {result.actual_balance})"
                    )
                )
                continue

            inconsistent += 1
            self.stderr.write(self.style.ERROR(f"wallet {wallet.pk}: INCONSISTENT"))
            for problem in result.problems:
                self.stderr.write(f"  - {problem}")

        if inconsistent:
            raise CommandError(f"{inconsistent} of {total} wallet(s) inconsistent")

        self.stdout.write(self.style.SUCCESS(f"All {total} wallet(s) consistent."))
