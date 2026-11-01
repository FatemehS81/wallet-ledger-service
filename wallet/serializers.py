from rest_framework import serializers

from wallet.models import LedgerEntry


class StrictIntegerField(serializers.IntegerField):
    """JSON integer only: strings, floats, booleans and null are rejected."""

    def to_internal_value(self, data):
        if isinstance(data, bool) or not isinstance(data, int):
            self.fail("invalid")
        return super().to_internal_value(data)


class TransactionRequestSerializer(serializers.Serializer):
    amount = StrictIntegerField(min_value=1)
    description = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default="",
    )


class LedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerEntry
        fields = ["id", "type", "amount", "balance_after", "description", "created_at"]


class BalanceSerializer(serializers.Serializer):
    balance = serializers.IntegerField()
    updated_at = serializers.DateTimeField()


class PaginatedLedgerEntrySerializer(serializers.Serializer):
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = LedgerEntrySerializer(many=True)
