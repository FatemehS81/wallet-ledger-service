import uuid

from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from core.serializers import ErrorResponseSerializer
from wallet import docs_examples as examples
from wallet import services
from wallet.exceptions import InvalidIdempotencyKey, WalletNotFound
from wallet.models import LedgerEntry, Wallet
from wallet.pagination import LedgerEntryCursorPagination
from wallet.serializers import (
    BalanceSerializer,
    LedgerEntrySerializer,
    PaginatedLedgerEntrySerializer,
    TransactionRequestSerializer,
)

IDEMPOTENCY_KEY_PARAMETER = OpenApiParameter(
    name="Idempotency-Key",
    type=str,
    location=OpenApiParameter.HEADER,
    required=True,
    description="Client-generated UUID, reused on every retry of the same operation.",
    examples=[OpenApiExample("Idempotency key", value=examples.CREDIT_IDEMPOTENCY_KEY)],
)

TRANSACTION_REQUEST_DESCRIPTION = (
    "Amount is an integer in minor units and must be a JSON integer, not a string. "
    "The Idempotency-Key header is required and must be a valid UUID."
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

    @extend_schema(
        tags=["Wallet"],
        summary="Credit the authenticated user's wallet",
        description=TRANSACTION_REQUEST_DESCRIPTION,
        request=TransactionRequestSerializer,
        parameters=[IDEMPOTENCY_KEY_PARAMETER],
        examples=examples.CREDIT_REQUEST_EXAMPLES,
        responses={
            201: OpenApiResponse(
                response=LedgerEntrySerializer,
                description="New ledger entry created.",
                examples=examples.CREDIT_CREATED_EXAMPLES,
            ),
            200: OpenApiResponse(
                response=LedgerEntrySerializer,
                description="Idempotent replay: the original entry is returned.",
                examples=examples.CREDIT_REPLAY_EXAMPLES,
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Invalid input, idempotency key or amount limit.",
                examples=[
                    examples.VALIDATION_ERROR_EXAMPLE,
                    examples.INVALID_IDEMPOTENCY_KEY_EXAMPLE,
                    examples.AMOUNT_LIMIT_EXCEEDED_EXAMPLE,
                ],
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                examples=[examples.NOT_AUTHENTICATED_EXAMPLE],
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                examples=[examples.WALLET_NOT_FOUND_EXAMPLE],
            ),
            409: OpenApiResponse(
                response=ErrorResponseSerializer,
                examples=[examples.IDEMPOTENCY_CONFLICT_EXAMPLE],
            ),
            422: OpenApiResponse(
                response=ErrorResponseSerializer,
                examples=[examples.BALANCE_LIMIT_EXCEEDED_EXAMPLE],
            ),
        },
    )
    def post(self, request):
        return super().post(request)


class DebitView(TransactionView):
    entry_type = LedgerEntry.Type.DEBIT

    @extend_schema(
        tags=["Wallet"],
        summary="Debit the authenticated user's wallet",
        description=TRANSACTION_REQUEST_DESCRIPTION,
        request=TransactionRequestSerializer,
        parameters=[IDEMPOTENCY_KEY_PARAMETER],
        examples=examples.DEBIT_REQUEST_EXAMPLES,
        responses={
            201: OpenApiResponse(
                response=LedgerEntrySerializer,
                description="New ledger entry created.",
                examples=examples.DEBIT_CREATED_EXAMPLES,
            ),
            200: OpenApiResponse(
                response=LedgerEntrySerializer,
                description="Idempotent replay: the original entry is returned.",
                examples=examples.DEBIT_REPLAY_EXAMPLES,
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Invalid input, idempotency key or amount limit.",
                examples=[
                    examples.VALIDATION_ERROR_EXAMPLE,
                    examples.INVALID_IDEMPOTENCY_KEY_EXAMPLE,
                    examples.AMOUNT_LIMIT_EXCEEDED_EXAMPLE,
                ],
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                examples=[examples.NOT_AUTHENTICATED_EXAMPLE],
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                examples=[examples.WALLET_NOT_FOUND_EXAMPLE],
            ),
            409: OpenApiResponse(
                response=ErrorResponseSerializer,
                examples=[examples.IDEMPOTENCY_CONFLICT_EXAMPLE],
            ),
            422: OpenApiResponse(
                response=ErrorResponseSerializer,
                examples=[examples.INSUFFICIENT_FUNDS_EXAMPLE],
            ),
        },
    )
    def post(self, request):
        return super().post(request)


class BalanceView(APIView):
    @extend_schema(
        tags=["Wallet"],
        summary="Get the authenticated user's current balance",
        responses={
            200: OpenApiResponse(
                response=BalanceSerializer,
                examples=examples.BALANCE_RESPONSE_EXAMPLES,
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                examples=[examples.NOT_AUTHENTICATED_EXAMPLE],
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                examples=[examples.WALLET_NOT_FOUND_EXAMPLE],
            ),
        },
    )
    def get(self, request):
        wallet = get_wallet_for_user(request.user)
        return Response(BalanceSerializer(wallet).data)


class TransactionListView(GenericAPIView):
    serializer_class = LedgerEntrySerializer
    pagination_class = LedgerEntryCursorPagination

    @extend_schema(
        tags=["Wallet"],
        summary="List the authenticated user's ledger history",
        description=(
            "Newest first, ordered by id. Cursor pagination is stable under "
            "concurrent inserts. The optional type filter accepts CREDIT or DEBIT."
        ),
        parameters=[
            OpenApiParameter(
                name="limit",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Page size, default 20, maximum 100.",
            ),
            OpenApiParameter(
                name="cursor",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Opaque cursor returned in the next/previous links.",
            ),
            OpenApiParameter(
                name="type",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                enum=["CREDIT", "DEBIT"],
                description="Only return entries of this type.",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=PaginatedLedgerEntrySerializer,
                examples=examples.TRANSACTIONS_RESPONSE_EXAMPLES,
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                examples=[examples.NOT_AUTHENTICATED_EXAMPLE],
            ),
            404: OpenApiResponse(
                response=ErrorResponseSerializer,
                examples=[examples.WALLET_NOT_FOUND_EXAMPLE],
            ),
        },
    )
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
