from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from auth.jwt_auth.jwt_service import JWTService
from auth.login_interface import (
    IdentityNotFoundError,
    InvalidCredentialsError,
    LoginProviderFactory,
    PasswordAuthError,
)
from database.service import RefreshTokenService, UserIdentityService, UserLoginLogService, UserService
from routes.auth_shared import _issue_token_response
from routes.dependencies import (
    get_identity_service,
    get_jwt_service,
    get_login_factory,
    get_login_log_service,
    get_refresh_token_service,
    get_user_service,
)
from routes.schemas import LoginRequest, RegisterRequest, TokenResponse


def register_password_routes(auth_router: APIRouter) -> None:
    @auth_router.post(
        "/register",
        response_model=TokenResponse,
        status_code=status.HTTP_201_CREATED,
        summary="以 Email + 密碼註冊",
    )
    async def register(
        body: RegisterRequest,
        request: Request,
        response: Response,
        factory: LoginProviderFactory = Depends(get_login_factory),
        user_svc: UserService = Depends(get_user_service),
        identity_svc: UserIdentityService = Depends(get_identity_service),
        jwt_svc: JWTService = Depends(get_jwt_service),
        refresh_token_svc: RefreshTokenService = Depends(get_refresh_token_service),
        log_svc: UserLoginLogService = Depends(get_login_log_service),
    ):
        try:
            pwd_provider = factory.get_password()
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="密碼登入功能未啟用",
            )

        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("User-Agent")

        weakness = pwd_provider.validate_password_strength(body.password)
        if weakness:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"密碼強度不足: {weakness}",
            )

        if body.terms_accepted is not True:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="請先同意服務條款及隱私政策",
            )

        existing_user = await user_svc.get_by_email(body.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="此 Email 已被註冊",
            )

        existing_identity = await identity_svc.get_by_provider("password", body.email)
        if existing_identity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="此 Email 已被註冊",
            )

        hashed_password = pwd_provider.hash_password(body.password)
        user = await user_svc.create_user(
            email=body.email,
            username=body.username,
            provider="password",
            provider_key=body.email,
            secret_hash=hashed_password,
            agreed_to_terms_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )

        await log_svc.log_login(
            user_id=user.id,
            identifier=body.email,
            status="success",
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return await _issue_token_response(
            user=user,
            response=response,
            jwt_svc=jwt_svc,
            refresh_token_svc=refresh_token_svc,
        )

    @auth_router.post(
        "/login",
        response_model=TokenResponse,
        summary="以 Email + 密碼登入",
    )
    async def login(
        body: LoginRequest,
        request: Request,
        response: Response,
        factory: LoginProviderFactory = Depends(get_login_factory),
        user_svc: UserService = Depends(get_user_service),
        jwt_svc: JWTService = Depends(get_jwt_service),
        refresh_token_svc: RefreshTokenService = Depends(get_refresh_token_service),
        log_svc: UserLoginLogService = Depends(get_login_log_service),
    ):
        try:
            pwd_provider = factory.get_password()
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="密碼登入功能未啟用",
            )

        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("User-Agent")

        try:
            user_by_identifier = await user_svc.get_by_identifier(body.identifier)
            resolved_identifier = (
                user_by_identifier.email
                if user_by_identifier and user_by_identifier.email
                else body.identifier
            )

            result = await pwd_provider.authenticate(
                identifier=resolved_identifier,
                password=body.password,
            )
        except (InvalidCredentialsError, IdentityNotFoundError):
            await log_svc.log_login(
                identifier=body.identifier,
                status="failed",
                failure_reason="invalid_credentials",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="帳號或密碼錯誤",
            )
        except PasswordAuthError as e:
            await log_svc.log_login(
                identifier=body.identifier,
                status="failed",
                failure_reason=e.message[:50],
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="帳號或密碼錯誤",
            )

        user = await user_svc.get_by_id(result.user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="使用者資料異常",
            )

        await log_svc.log_login(
            user_id=user.id,
            identifier=body.identifier,
            status="success",
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return await _issue_token_response(
            user=user,
            response=response,
            jwt_svc=jwt_svc,
            refresh_token_svc=refresh_token_svc,
        )
