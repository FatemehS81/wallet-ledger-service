import uuid

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from wallet import services
from wallet.exceptions import InvalidIdempotencyKey, WalletNotFound
from wallet.models import LedgerEntry, Wallet
from wallet.pagination import LedgerEntryCursorPagination
from wallet.serializers import (
    BalanceSerializer,
    LedgerEntrySerializer,
    TransactionRequestSerializer,
)


def get_wallet_for_user(user) -> Wallet:
    try:
        return Wallet.objects.get(user=user)
    except Wallet.DoesNotExist:
        raise WalletNotFound("The user has no wallet.") from None


def parse_idempotency_key(request) -> uuid.UUID:
    raw_key = request.headers.get("Idempotency-Key")
    if not raw_key:
        raise InvalidIdempotencyKey("Idempotency-Key header is required.")
    try:
        return uuid.UUID(raw_key)
    except (ValueError, TypeError, AttributeError):
        raise InvalidIdempotencyKey("Idempotency-Key must be a valid UUID.") from None


class TransactionView(APIView):
    entry_type: str

    def post(self, request):
        serializer = TransactionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        idempotency_key = parse_idempotency_key(request)

        if self.entry_type == LedgerEntry.Type.CREDIT:
            entry, created = services.credit(
                request.user,
                serializer.validated_data["amount"],
                idempotency_key,
                serializer.validated_data["description"],
            )
        else:
            entry, created = services.debit(
                request.user,
                serializer.validated_data["amount"],
                idempotency_key,
                serializer.validated_data["description"],
            )

        http_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(LedgerEntrySerializer(entry).data, status=http_status)


class CreditView(TransactionView):
    entry_type = LedgerEntry.Type.CREDIT


class DebitView(TransactionView):
    entry_type = LedgerEntry.Type.DEBIT


class BalanceView(APIView):
    def get(self, request):
        wallet = get_wallet_for_user(request.user)
        return Response(BalanceSerializer(wallet).data)


class TransactionListView(GenericAPIView):
    serializer_class = LedgerEntrySerializer
    pagination_class = LedgerEntryCursorPagination

    def get(self, request):
        wallet = get_wallet_for_user(request.user)
        queryset = LedgerEntry.objects.filter(wallet=wallet)

        entry_type = request.query_params.get("type")
        if entry_type is not None:
            if entry_type not in LedgerEntry.Type.values:
                raise ValidationError(
                    {"type": [f"Must be one of: {', '.join(LedgerEntry.Type.values)}."]}
                )
            queryset = queryset.filter(type=entry_type)

        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)
