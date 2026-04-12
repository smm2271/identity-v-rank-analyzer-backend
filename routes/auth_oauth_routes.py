import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from auth.jwt_auth.jwt_service import JWTService
from auth.login_interface import (
    IdentityNotFoundError,
    InvalidCredentialsError,
    LoginProviderFactory,
    OAuthError,
    PasswordAuthError,
)
from database.service import (
    RefreshTokenService,
    UserIdentityService,
    UserLoginLogService,
    UserService,
)
from routes.auth_shared import (
    _build_oauth_flow_token,
    _generate_signed_state,
    _issue_token_response,
    _link_identity_after_oauth_verification,
    _verify_oauth_flow_token,
    _verify_signed_state,
)
from routes.dependencies import (
    get_identity_service,
    get_jwt_service,
    get_login_factory,
    get_login_log_service,
    get_refresh_token_service,
    get_user_service,
)
from routes.schemas import (
    OAuthAuthorizeResponse,
    OAuthFinalizeRequest,
    OAuthLinkRequest,
    ProvidersResponse,
    TokenResponse,
)


def register_oauth_routes(auth_router: APIRouter) -> None:
    @auth_router.get(
        "/providers",
        response_model=ProvidersResponse,
        summary="列出可用的登入供應商",
    )
    async def list_providers(
        factory: LoginProviderFactory = Depends(get_login_factory),
    ):
        return ProvidersResponse(
            oauth_providers=factory.list_oauth_providers(),
            password_enabled=factory.has("password"),
        )

    @auth_router.get(
        "/{provider}/authorize",
        response_model=OAuthAuthorizeResponse,
        summary="取得 OAuth 授權 URL",
    )
    async def oauth_authorize(
        provider: str,
        redirect_uri: str = Query(..., description="OAuth 授權完成後的回呼 URL"),
        factory: LoginProviderFactory = Depends(get_login_factory),
    ):
        try:
            oauth_provider = factory.get_oauth(provider)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支援的 OAuth 供應商: {provider}",
            )

        state = _generate_signed_state()

        try:
            auth_url = await oauth_provider.get_authorization_url(
                redirect_uri=redirect_uri,
                state=state,
            )
        except OAuthError as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"無法產生授權 URL: {e.message}",
            )

        return OAuthAuthorizeResponse(
            authorization_url=auth_url.url,
            state=auth_url.state,
        )

    @auth_router.get(
        "/{provider}/callback",
        response_model=TokenResponse,
        summary="OAuth 回呼處理",
    )
    async def oauth_callback(
        provider: str,
        code: str = Query(..., description="OAuth authorization code"),
        state: str = Query(..., description="CSRF state 參數"),
        redirect_uri: str = Query(..., description="與 authorize 時使用的相同回呼 URL"),
        link_token: str | None = Query(None, description="待關聯 OAuth 流程 token（驗證模式使用）"),
        request: Request = None,  # type: ignore[assignment]
        response: Response = None,  # type: ignore[assignment]
        factory: LoginProviderFactory = Depends(get_login_factory),
        user_svc: UserService = Depends(get_user_service),
        identity_svc: UserIdentityService = Depends(get_identity_service),
        jwt_svc: JWTService = Depends(get_jwt_service),
        refresh_token_svc: RefreshTokenService = Depends(get_refresh_token_service),
        log_svc: UserLoginLogService = Depends(get_login_log_service),
    ):
        try:
            oauth_provider = factory.get_oauth(provider)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支援的 OAuth 供應商: {provider}",
            )

        if not _verify_signed_state(state):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="無效或過期的 state 參數，請重新發起授權流程",
            )

        ip_address = request.client.host if request and request.client else None
        user_agent = request.headers.get("User-Agent") if request else None

        try:
            tokens = await oauth_provider.exchange_code(
                code=code,
                redirect_uri=redirect_uri,
            )

            user_info = await oauth_provider.fetch_user_info(
                access_token=tokens.access_token,
            )
        except OAuthError as e:
            await log_svc.log_login(
                identifier=f"{provider}:unknown",
                status="failed",
                failure_reason=e.message[:50],
                ip_address=ip_address,
                user_agent=user_agent,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"OAuth 驗證失敗: {e.message}",
            )

        identity = await identity_svc.get_by_provider(
            provider=user_info.provider,
            provider_key=user_info.provider_key,
        )

        if identity is None:
            secret_hash = None
            if tokens.refresh_token:
                secret_hash = hashlib.sha256(
                    tokens.refresh_token.encode()
                ).hexdigest()

            existing_user = None
            if user_info.email:
                existing_user = await user_svc.get_by_email(user_info.email)

            if not user_info.email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="OAuth 供應商未提供 Email，無法完成後續流程",
                )

            if existing_user is not None:
                existing_identities = await identity_svc.get_all_by_user(existing_user.id)
                verification_oauth_providers = sorted(
                    {
                        item.provider
                        for item in existing_identities
                        if item.provider not in {"password", user_info.provider}
                    }
                )
                pending_link_token = _build_oauth_flow_token(
                    kind="link",
                    provider=user_info.provider,
                    provider_key=user_info.provider_key,
                    email=user_info.email,
                    username=user_info.username,
                    secret_hash=secret_hash,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": "LINK_REQUIRED",
                        "message": "此 Email 已被其他帳號使用，請先以原有第三方帳號完成驗證後再關聯",
                        "link_token": pending_link_token,
                        "provider": user_info.provider,
                        "email": user_info.email,
                        "verification_oauth_providers": verification_oauth_providers,
                    },
                )
            registration_token = _build_oauth_flow_token(
                kind="registration",
                provider=user_info.provider,
                provider_key=user_info.provider_key,
                email=user_info.email,
                username=user_info.username,
                secret_hash=secret_hash,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "REGISTRATION_REQUIRED",
                    "message": "請先完成基本資料設定",
                    "registration_token": registration_token,
                    "provider": user_info.provider,
                    "email": user_info.email,
                },
            )
        else:
            user = await user_svc.get_by_id(identity.user_id)
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="身份對應的使用者不存在",
                )

            if link_token is not None:
                await _link_identity_after_oauth_verification(
                    link_token=link_token,
                    user=user,
                    verified_provider=user_info.provider,
                    verified_provider_key=user_info.provider_key,
                    identity_svc=identity_svc,
                )

        await log_svc.log_login(
            user_id=user.id,
            identifier=f"{user_info.provider}:{user_info.provider_key}",
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
        "/oauth-finalize",
        response_model=TokenResponse,
        status_code=status.HTTP_201_CREATED,
        summary="完成 OAuth 新用戶註冊",
    )
    async def oauth_finalize(
        body: OAuthFinalizeRequest,
        request: Request,
        response: Response,
        user_svc: UserService = Depends(get_user_service),
        identity_svc: UserIdentityService = Depends(get_identity_service),
        jwt_svc: JWTService = Depends(get_jwt_service),
        refresh_token_svc: RefreshTokenService = Depends(get_refresh_token_service),
        log_svc: UserLoginLogService = Depends(get_login_log_service),
    ):
        pending = _verify_oauth_flow_token(body.registration_token, "registration")
        if pending is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="註冊暫存資料已失效或無效，請重新登入",
            )

        if body.terms_accepted is not True:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="請先同意服務條款及隱私政策",
            )

        existing_user = await user_svc.get_by_email(pending["email"])
        if existing_user is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="此 Email 已被註冊，請改用帳號關聯流程",
            )

        existing_identity = await identity_svc.get_by_provider(
            pending["provider"],
            pending["provider_key"],
        )
        if existing_identity is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="此 OAuth 身分已被使用，請重新登入",
            )

        user = await user_svc.create_user(
            email=pending["email"],
            username=body.username,
            provider=pending["provider"],
            provider_key=pending["provider_key"],
            secret_hash=pending.get("secret_hash"),
            agreed_to_terms_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )

        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("User-Agent")
        await log_svc.log_login(
            user_id=user.id,
            identifier=f"{pending['provider']}:{pending['provider_key']}",
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
        "/link-identity",
        response_model=TokenResponse,
        summary="關聯 OAuth 身分",
    )
    async def link_identity(
        body: OAuthLinkRequest,
        request: Request,
        response: Response,
        factory: LoginProviderFactory = Depends(get_login_factory),
        user_svc: UserService = Depends(get_user_service),
        identity_svc: UserIdentityService = Depends(get_identity_service),
        jwt_svc: JWTService = Depends(get_jwt_service),
        refresh_token_svc: RefreshTokenService = Depends(get_refresh_token_service),
        log_svc: UserLoginLogService = Depends(get_login_log_service),
    ):
        pending = _verify_oauth_flow_token(body.link_token, "link")
        if pending is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="關聯暫存資料已失效或無效，請重新登入",
            )

        try:
            pwd_provider = factory.get_password()
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="密碼登入功能未啟用",
            )

        user_by_identifier = await user_svc.get_by_identifier(body.identifier)
        resolved_identifier = (
            user_by_identifier.email
            if user_by_identifier and user_by_identifier.email
            else body.identifier
        )

        try:
            result = await pwd_provider.authenticate(
                identifier=resolved_identifier,
                password=body.password,
            )
        except (InvalidCredentialsError, IdentityNotFoundError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="帳號或密碼錯誤",
            )
        except PasswordAuthError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"帳號或密碼錯誤: {e.message}",
            )

        identity = await identity_svc.get_by_provider(pending["provider"], pending["provider_key"])
        if identity is not None and identity.user_id != result.user_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="此 OAuth 身分已被其他帳號綁定",
            )

        if identity is None:
            await identity_svc.create_identity(
                user_id=result.user_id,
                provider=pending["provider"],
                provider_key=pending["provider_key"],
                secret_hash=pending.get("secret_hash"),
            )

        user = await user_svc.get_by_id(result.user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="使用者資料異常",
            )

        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("User-Agent")
        await log_svc.log_login(
            user_id=user.id,
            identifier=f"{pending['provider']}:{pending['provider_key']}",
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
