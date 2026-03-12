"""
Route Dependencies
==================
FastAPI 依賴注入元件，**集中管理**所有路由共用的 Service 取用與身分驗證邏輯。

═══════════════════════════════════════════════════
SOLID 原則對應
═══════════════════════════════════════════════════

(S) 單一職責
    本模組的**唯一職責**是「管理依賴注入容器 + 提供身分驗證依賴」。
    - 不含任何業務邏輯（委派給 Service 層）
    - 不含任何路由定義（由 auth_routes.py / user_routes.py 負責）
    - 不含任何 Pydantic Schema（由 schemas.py 負責）

(O) 開放封閉
    新增 Service 只需新增一個 getter 函式並在 init_dependencies() 加入參數，
    **既有的 getter 函式不需修改**。

(D) 依賴反轉
    路由模組**不直接 import** database.database.AsyncSessionLocal 來建構 Service，
    而是透過本模組的 getter 函式取得由 app.py 注入的實例。
    這使得路由層與具體資料庫連線設定完全解耦，有利於測試時替換 mock。

(I) 介面隔離
    各 getter 函式各自獨立，路由端點只 Depends() 所需的 Service，
    不會被迫依賴不相關的 Service。
"""

import hashlib
import uuid

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

from auth.jwt_auth.jwt_service import (
    JWTService,
    TokenError,
    TokenExpiredError,
    TokenInvalidError,
    TokenRevokedError,
)
from auth.login_interface import LoginProviderFactory
from database.service import (
    ApiKeyService,
    GameMatchService,
    UserIdentityService,
    UserLoginLogService,
    UserService,
)


# ══════════════════════════════════════════════════
# 依賴注入容器
# ══════════════════════════════════════════════════
# (D) 依賴反轉：所有 Service 實例由 app.py 啟動時透過 init_dependencies() 注入，
#     路由模組透過下方的 getter 函式取用，**不自行建構**，達到鬆耦合。
# ══════════════════════════════════════════════════

_user_service: UserService | None = None
_identity_service: UserIdentityService | None = None
_login_log_service: UserLoginLogService | None = None
_jwt_service: JWTService | None = None
_login_factory: LoginProviderFactory | None = None
_api_key_service: ApiKeyService | None = None
_match_service: GameMatchService | None = None


def init_dependencies(
    *,
    user_service: UserService,
    identity_service: UserIdentityService,
    login_log_service: UserLoginLogService,
    jwt_service: JWTService,
    login_factory: LoginProviderFactory,
    api_key_service: ApiKeyService,
    match_service: GameMatchService,
) -> None:
    """
    由 app.py 啟動時呼叫一次，注入所有 Service 實例。

    (D) 依賴反轉：app.py（組合根）負責建構所有具體 Service，
    本模組只接收並持有，不知道也不關心它們如何被建構。
    """
    global _user_service, _identity_service, _login_log_service
    global _jwt_service, _login_factory, _api_key_service, _match_service
    _user_service = user_service
    _identity_service = identity_service
    _login_log_service = login_log_service
    _jwt_service = jwt_service
    _login_factory = login_factory
    _api_key_service = api_key_service
    _match_service = match_service


# ──────────────────────────────────────────────
# Service Getter 函式
# ──────────────────────────────────────────────
# (I) 介面隔離：每個 Service 有獨立的 getter，
#     路由端點只 Depends() 實際需要的 Service。
# ──────────────────────────────────────────────

def get_user_service() -> UserService:
    assert _user_service is not None, "UserService 尚未初始化，請先呼叫 init_dependencies()"
    return _user_service


def get_identity_service() -> UserIdentityService:
    assert _identity_service is not None, "UserIdentityService 尚未初始化"
    return _identity_service


def get_login_log_service() -> UserLoginLogService:
    assert _login_log_service is not None, "UserLoginLogService 尚未初始化"
    return _login_log_service


def get_jwt_service() -> JWTService:
    assert _jwt_service is not None, "JWTService 尚未初始化"
    return _jwt_service


def get_login_factory() -> LoginProviderFactory:
    assert _login_factory is not None, "LoginProviderFactory 尚未初始化"
    return _login_factory


def get_api_key_service() -> ApiKeyService:
    assert _api_key_service is not None, "ApiKeyService 尚未初始化"
    return _api_key_service


def get_match_service() -> GameMatchService:
    assert _match_service is not None, "GameMatchService 尚未初始化"
    return _match_service


# ══════════════════════════════════════════════════
# 身分驗證依賴
# ══════════════════════════════════════════════════
# (S) 單一職責：每個驗證函式只負責「一種」驗證方式。
# (O) 開放封閉：新增驗證方式（如 OAuth Token 驗證）只需新增函式，
#     不需修改 get_current_user 或 verify_api_key。
# ══════════════════════════════════════════════════


async def get_current_user(
    request: Request,
    jwt_svc: JWTService = Depends(get_jwt_service),
    user_svc: UserService = Depends(get_user_service),
):
    """
    FastAPI 依賴：從 Authorization header 解析 JWT 並取得當前使用者。

    (S) 單一職責：僅負責「JWT Bearer Token → User 物件」的轉換，
        不處理任何業務邏輯。
    (D) 依賴反轉：透過 Depends() 取得 JWTService 與 UserService，
        不直接持有或建構它們。

    Header 格式: Authorization: Bearer <access_token>

    Raises:
        HTTPException 401: Token 缺失、過期、無效或已被撤銷
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少有效的 Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header.removeprefix("Bearer ").strip()

    try:
        payload = await jwt_svc.verify_and_check_revocation(token, user_svc)
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 已過期，請使用 refresh token 換發新 token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except TokenRevokedError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 已被撤銷，請重新登入",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (TokenInvalidError, TokenError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 無效",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 確保 token 類型為 access
    if payload.token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="請使用 access token 進行 API 請求",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await user_svc.get_by_id(payload.uuid)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="使用者不存在",
        )

    return user


# ── API Key 驗證 ─────────────────────────────

# (S) 單一職責：僅定義 header 解析方式
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _hash_api_key(raw_key: str) -> str:
    """(S) 單一職責：僅負責雜湊邏輯"""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


async def verify_api_key(
    api_key: str | None = Security(api_key_header),
    api_key_svc: ApiKeyService = Depends(get_api_key_service),
) -> uuid.UUID:
    """
    驗證 API Key 並回傳對應的 user_id。

    (S) 單一職責：僅做「驗證 → 回傳 user_id」，不處理業務邏輯。
    (D) 依賴反轉：透過 FastAPI Depends 取得 ApiKeyService。

    Raises:
        HTTPException 401: 未提供 API Key
        HTTPException 403: API Key 無效或已停用
    """
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key. Please provide X-API-Key header.",
        )

    key_hash = _hash_api_key(api_key)
    record = await api_key_svc.get_by_key_hash(key_hash)

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or inactive API Key.",
        )

    # 更新最後使用時間
    await api_key_svc.touch_last_used(record.id)

    return record.user_id
