from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.views import (
    TokenBlacklistView,
    TokenObtainPairView,
    TokenRefreshView,
)

from accounts.serializers import (
    LoginRequestSerializer,
    LogoutRequestSerializer,
    RefreshRequestSerializer,
    RegisterSerializer,
    TokenPairSerializer,
    UserSerializer,
)
from accounts.services import register_user
from core.serializers import ErrorResponseSerializer
from wallet import docs_examples as examples


class RegisterView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        tags=["Auth"],
        summary="Register a user and their wallet",
        description="Creates the user and the wallet in one transaction.",
        request=RegisterSerializer,
        examples=examples.REGISTER_REQUEST_EXAMPLES,
        responses={
            201: OpenApiResponse(
                response=UserSerializer,
                examples=examples.REGISTER_RESPONSE_EXAMPLES,
            ),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                description="Invalid input or username already taken.",
                examples=[
                    examples.USERNAME_TAKEN_EXAMPLE,
                    examples.VALIDATION_ERROR_EXAMPLE,
                ],
            ),
        },
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = register_user(
            serializer.validated_data["username"],
            serializer.validated_data["password"],
        )
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    post=extend_schema(
        tags=["Auth"],
        summary="Log in",
        description="Returns an access token and a refresh token.",
        request=LoginRequestSerializer,
        examples=examples.LOGIN_REQUEST_EXAMPLES,
        responses={
            200: OpenApiResponse(
                response=TokenPairSerializer,
                examples=examples.LOGIN_RESPONSE_EXAMPLES,
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                examples=[examples.NOT_AUTHENTICATED_EXAMPLE],
            ),
        },
    )
)
class LoginView(TokenObtainPairView):
    pass


@extend_schema_view(
    post=extend_schema(
        tags=["Auth"],
        summary="Refresh tokens",
        description="Rotates the refresh token; the old refresh token is blacklisted.",
        request=RefreshRequestSerializer,
        examples=examples.REFRESH_REQUEST_EXAMPLES,
        responses={
            200: OpenApiResponse(
                response=TokenPairSerializer,
                examples=examples.REFRESH_RESPONSE_EXAMPLES,
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                examples=[examples.NOT_AUTHENTICATED_EXAMPLE],
            ),
        },
    )
)
class RefreshView(TokenRefreshView):
    pass


@extend_schema_view(
    post=extend_schema(
        tags=["Auth"],
        summary="Log out",
        description="Blacklists the supplied refresh token. Requires a valid access token.",
        request=LogoutRequestSerializer,
        examples=examples.LOGOUT_REQUEST_EXAMPLES,
        responses={
            200: OpenApiResponse(description="Refresh token blacklisted."),
            400: OpenApiResponse(
                response=ErrorResponseSerializer,
                examples=[examples.VALIDATION_ERROR_EXAMPLE],
            ),
            401: OpenApiResponse(
                response=ErrorResponseSerializer,
                examples=[examples.NOT_AUTHENTICATED_EXAMPLE],
            ),
        },
    )
)
class LogoutView(TokenBlacklistView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
