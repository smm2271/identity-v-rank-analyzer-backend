"""
Auth Routes
===========
認證相關的 API 路由。

═══════════════════════════════════════════════════
SOLID 原則對應
═══════════════════════════════════════════════════

(S) 單一職責
    本模組**僅**負責「認證」相關的 HTTP 端點定義與請求/回應轉換：
    - OAuth2 授權流程（authorize / callback）
    - 密碼登入 / 註冊
    - Token 刷新 / 登出
    所有實際業務邏輯委派給 Service 層（JWTService、LoginProviderFactory 等）。
    Pydantic Schema 獨立於 schemas.py，DI 邏輯獨立於 dependencies.py。

(O) 開放封閉
    新增 OAuth 供應商（如 GitHub、Apple）時，只需在 LoginProviderFactory 註冊，
    本模組的路由程式碼**完全不需修改**，因為路由透過 factory.get_oauth(provider)
    動態取得供應商實例（開放擴展、封閉修改）。

(L) 里氏替換
    oauth_callback 中透過 OAuthLoginInterface 抽象呼叫 exchange_code / fetch_user_info，
    Google、Discord 或任何新供應商都可互相替換，路由層無需感知具體實作。

(D) 依賴反轉
    所有 Service（UserService、JWTService 等）透過 FastAPI Depends() 從
    dependencies.py 的 getter 函式取得，本模組**不 import 任何具體建構邏輯**。
"""

import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from auth.jwt_auth.jwt_service import (
    JWTService,
    TokenError,
    TokenExpiredError,
    TokenInvalidError,
    TokenRevokedError,
)
from auth.login_interface import (
    LoginProviderFactory,
    OAuthError,
    PasswordAuthError,
    InvalidCredentialsError,
    IdentityNotFoundError,
)
from database.service import (
    UserService,
    UserIdentityService,
    UserLoginLogService,
)
from routes.dependencies import (
    get_current_user,
    get_identity_service,
    get_jwt_service,
    get_login_factory,
    get_login_log_service,
    get_user_service,
)
from routes.schemas import (
    LoginRequest,
    MessageResponse,
    OAuthAuthorizeResponse,
    ProvidersResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)

# ──────────────────────────────────────────────
# OAuth State CSRF 防護
# ──────────────────────────────────────────────
# 使用 HMAC 簽名機制產生與驗證 state 參數，無需伺服端儲存。
# state 格式: {nonce}:{timestamp}:{hmac_signature}
# ──────────────────────────────────────────────

_STATE_SECRET = os.getenv("OAUTH_STATE_SECRET", secrets.token_urlsafe(32))
_STATE_MAX_AGE_SECONDS = 600  # state 有效期 10 分鐘


def _generate_signed_state() -> str:
    """產生 HMAC 簽名的 OAuth state 參數（防 CSRF）。"""
    nonce = secrets.token_urlsafe(16)
    timestamp = str(int(time.time()))
    message = f"{nonce}:{timestamp}"
    signature = hmac.new(
        _STATE_SECRET.encode(), message.encode(), hashlib.sha256
    ).hexdigest()
    return f"{nonce}:{timestamp}:{signature}"


def _verify_signed_state(state: str) -> bool:
    """驗證 HMAC 簽名的 OAuth state 參數是否合法且未過期。"""
    try:
        parts = state.split(":")
        if len(parts) != 3:
            return False
        nonce, timestamp, signature = parts
        # 檢查是否過期
        if int(time.time()) - int(timestamp) > _STATE_MAX_AGE_SECONDS:
            return False
        # 驗證 HMAC 簽名
        message = f"{nonce}:{timestamp}"
        expected = hmac.new(
            _STATE_SECRET.encode(), message.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature, expected)
    except Exception:
        return False


# ──────────────────────────────────────────────
# Router 定義 (S: 僅作為路由的命名空間)
# ──────────────────────────────────────────────
auth_router = APIRouter(prefix="/auth", tags=["Auth"])


# ══════════════════════════════════════════════════
# OAuth2 Routes
# ══════════════════════════════════════════════════
# (O) 開放封閉：以下端點透過 LoginProviderFactory 動態路由到各供應商，
#     新增供應商不需修改任何路由程式碼。
# ══════════════════════════════════════════════════


@auth_router.get(
    "/providers",
    response_model=ProvidersResponse,
    summary="列出可用的登入供應商",
)
async def list_providers(
    factory: LoginProviderFactory = Depends(get_login_factory),
):
    """
    回傳所有已註冊的 OAuth 供應商名稱及密碼登入是否啟用。

    (O) 開放封閉：供應商列表由 Factory 動態提供，新增供應商後此端點自動反映。
    """
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
    """
    產生指定 OAuth 供應商的授權 URL。

    (L) 里氏替換：無論是 Google 或 Discord，都透過相同的
        OAuthLoginInterface.get_authorization_url() 呼叫，行為一致。

    前端應將使用者重導向至回傳的 authorization_url。
    state 參數由後端產生，前端需在回呼時帶回以防 CSRF。
    """
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
    request: Request = None,  # type: ignore[assignment]
    factory: LoginProviderFactory = Depends(get_login_factory),
    user_svc: UserService = Depends(get_user_service),
    identity_svc: UserIdentityService = Depends(get_identity_service),
    jwt_svc: JWTService = Depends(get_jwt_service),
    log_svc: UserLoginLogService = Depends(get_login_log_service),
):
    """
    處理 OAuth 授權回呼。

    (S) 單一職責：本函式只做 HTTP 層的「請求解析 → 委派 Service → 回應組裝」。
    (L) 里氏替換：exchange_code / fetch_user_info 透過 OAuthLoginInterface 抽象呼叫，
        Google 與 Discord 可無縫替換。
    (D) 依賴反轉：所有 Service 透過 Depends() 注入，不直接持有。

    流程：
    1. 以 authorization code 向供應商交換 tokens
    2. 以 access_token 取得使用者資訊
    3. 查詢 user_identities 是否已有此身份
    4. 若無 → 建立新使用者 + 身份
    5. 簽發 JWT access + refresh token
    """
    # 取得 provider 實例
    try:
        oauth_provider = factory.get_oauth(provider)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支援的 OAuth 供應商: {provider}",
        )

    # 驗證 state 參數（防止 CSRF 攻擊）
    if not _verify_signed_state(state):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="無效或過期的 state 參數，請重新發起授權流程",
        )

    ip_address = request.client.host if request and request.client else None
    user_agent = request.headers.get("User-Agent") if request else None

    try:
        # Step 1: 交換 code → tokens
        tokens = await oauth_provider.exchange_code(
            code=code,
            redirect_uri=redirect_uri,
        )

        # Step 2: 取得使用者資訊
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

    # Step 3: 查詢是否已有此身份
    identity = await identity_svc.get_by_provider(
        provider=user_info.provider,
        provider_key=user_info.provider_key,
    )

    if identity is None:
        # Step 4a: 新使用者 — 建立 User + UserIdentity
        secret_hash = None
        if tokens.refresh_token:
            secret_hash = hashlib.sha256(
                tokens.refresh_token.encode()
            ).hexdigest()

        user = await user_svc.create_user(
            email=user_info.email,
            username=user_info.username,
            provider=user_info.provider,
            provider_key=user_info.provider_key,
            secret_hash=secret_hash,
            agreed_to_terms_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
    else:
        # Step 4b: 既有使用者
        user = await user_svc.get_by_id(identity.user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="身份對應的使用者不存在",
            )

    # Step 5: 簽發 JWT
    token_pair = jwt_svc.create_token_pair(user_uuid=user.id, token_ver=user.token_ver, user_name=user.username or "")

    await log_svc.log_login(
        user_id=user.id,
        identifier=f"{user_info.provider}:{user_info.provider_key}",
        status="success",
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return TokenResponse(
        access_token=token_pair["access_token"],
        refresh_token=token_pair["refresh_token"],
    )


# ══════════════════════════════════════════════════
# Password Auth Routes
# ══════════════════════════════════════════════════


@auth_router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="以 Email + 密碼註冊",
)
async def register(
    body: RegisterRequest,
    request: Request,
    factory: LoginProviderFactory = Depends(get_login_factory),
    user_svc: UserService = Depends(get_user_service),
    identity_svc: UserIdentityService = Depends(get_identity_service),
    jwt_svc: JWTService = Depends(get_jwt_service),
    log_svc: UserLoginLogService = Depends(get_login_log_service),
):
    """
    以 Email + 密碼註冊新帳號。

    (S) 單一職責：本函式僅協調各 Service 完成註冊流程，
        密碼強度驗證委派給 PasswordLoginProvider，
        使用者建立委派給 UserService。
    (D) 依賴反轉：密碼供應商透過 factory.get_password() 取得，
        不直接依賴 PasswordLoginProvider 具體類別。
    """
    try:
        pwd_provider = factory.get_password()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="密碼登入功能未啟用",
        )

    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    # Step 1: 密碼強度檢查（委派給 PasswordLoginProvider）
    weakness = pwd_provider.validate_password_strength(body.password)
    if weakness:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"密碼強度不足: {weakness}",
        )

    # Step 2: Email 唯一性檢查
    existing_user = await user_svc.get_by_email(body.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="此 Email 已被註冊",
        )

    # Step 3: 檢查是否已存在 password identity
    existing_identity = await identity_svc.get_by_provider("password", body.email)
    if existing_identity:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="此 Email 已被註冊",
        )

    # Step 4: 建立使用者（委派給 UserService）
    hashed_password = pwd_provider.hash_password(body.password)
    user = await user_svc.create_user(
        email=body.email,
        username=body.username,
        provider="password",
        provider_key=body.email,
        secret_hash=hashed_password,
        agreed_to_terms_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )

    # Step 5: 簽發 JWT
    token_pair = jwt_svc.create_token_pair(user.id, user.token_ver, user_name=user.username or "")

    await log_svc.log_login(
        user_id=user.id,
        identifier=body.email,
        status="success",
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return TokenResponse(
        access_token=token_pair["access_token"],
        refresh_token=token_pair["refresh_token"],
    )


@auth_router.post(
    "/login",
    response_model=TokenResponse,
    summary="以 Email + 密碼登入",
)
async def login(
    body: LoginRequest,
    request: Request,
    factory: LoginProviderFactory = Depends(get_login_factory),
    user_svc: UserService = Depends(get_user_service),
    jwt_svc: JWTService = Depends(get_jwt_service),
    log_svc: UserLoginLogService = Depends(get_login_log_service),
):
    """
    以 Email + 密碼登入。

    (S) 單一職責：本函式只負責 HTTP 層的流程協調，
        帳密驗證完全委派給 PasswordLoginProvider.authenticate()。
    (D) 依賴反轉：密碼供應商透過 Factory 取得。

    安全考量：無論帳號不存在或密碼錯誤，統一回傳「帳號或密碼錯誤」，
    防止帳號列舉攻擊。
    """
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
        result = await pwd_provider.authenticate(
            identifier=body.email,
            password=body.password,
        )
    except (InvalidCredentialsError, IdentityNotFoundError):
        await log_svc.log_login(
            identifier=body.email,
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
            identifier=body.email,
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

    token_pair = jwt_svc.create_token_pair(user.id, user.token_ver, user_name=user.username or "")

    await log_svc.log_login(
        user_id=user.id,
        identifier=body.email,
        status="success",
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return TokenResponse(
        access_token=token_pair["access_token"],
        refresh_token=token_pair["refresh_token"],
    )


# ══════════════════════════════════════════════════
# Token Management Routes
# ══════════════════════════════════════════════════


@auth_router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="以 Refresh Token 換發新 Token",
)
async def refresh_token(
    body: RefreshRequest,
    jwt_svc: JWTService = Depends(get_jwt_service),
    user_svc: UserService = Depends(get_user_service),
):
    """
    以 Refresh Token 換發新的 Access + Refresh Token 組合。

    (D) 依賴反轉：JWTService 與 UserService 透過 Depends() 注入。
    """
    try:
        payload = await jwt_svc.verify_and_check_revocation(
            body.refresh_token, user_svc
        )
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token 已過期，請重新登入",
        )
    except TokenRevokedError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 已被撤銷，請重新登入",
        )
    except (TokenInvalidError, TokenError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token 無效",
        )

    if payload.token_type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="請提供 refresh token，而非 access token",
        )

    user = await user_svc.get_by_id(payload.uuid)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="使用者不存在",
        )

    token_pair = jwt_svc.create_token_pair(user.id, user.token_ver, user_name=user.username or "")

    return TokenResponse(
        access_token=token_pair["access_token"],
        refresh_token=token_pair["refresh_token"],
    )


@auth_router.post(
    "/logout",
    response_model=MessageResponse,
    summary="登出（撤銷所有 Token）",
)
async def logout(
    current_user=Depends(get_current_user),
    user_svc: UserService = Depends(get_user_service),
):
    """
    登出當前使用者。

    透過遞增 token_ver 使所有已簽發的 JWT 立即失效（全裝置登出）。
    (S) 單一職責：僅協調 UserService.increment_token_ver()，不含其他邏輯。
    """
    await user_svc.increment_token_ver(current_user.id)

    return MessageResponse(message="已成功登出")
