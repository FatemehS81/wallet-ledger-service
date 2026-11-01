from django.urls import path

from wallet.views import BalanceView, CreditView, DebitView, TransactionListView

urlpatterns = [
    path("wallet/credit", CreditView.as_view(), name="wallet-credit"),
    path("wallet/debit", DebitView.as_view(), name="wallet-debit"),
    path("wallet/balance", BalanceView.as_view(), name="wallet-balance"),
    path("wallet/transactions", TransactionListView.as_view(), name="wallet-transactions"),
]
