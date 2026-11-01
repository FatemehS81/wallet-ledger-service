from rest_framework import serializers


class ErrorDetailSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    details = serializers.DictField()


class ErrorResponseSerializer(serializers.Serializer):
    """The uniform error envelope returned by every endpoint."""

    error = ErrorDetailSerializer()
