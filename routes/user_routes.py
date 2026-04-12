"""
User Routes
===========
使用者資訊相關的 API 路由。

═══════════════════════════════════════════════════
SOLID 原則對應
═══════════════════════════════════════════════════

(S) 單一職責
    本模組**僅**負責「已登入使用者」的資料與 API Key 管理端點：
    - GET /users/me             — 取得當前使用者資料
    - GET /users/me/identities  — 取得當前使用者的所有身份驗證來源
    - POST /users/me/api-keys   — 建立 API Key
    - GET /users/me/api-keys    — 列出 API Keys
    - DELETE /users/me/api-keys/{key_id} — 停用 API Key
    不包含認證路由（在 auth_routes.py）、Schema 定義（在 schemas.py）、
    或 DI 邏輯（在 dependencies.py）。

(D) 依賴反轉
    所有 Service 透過 dependencies.py 的 getter 函式以 Depends() 注入，
    本模組不直接 import 任何具體建構邏輯。

(I) 介面隔離
    每個端點只 Depends() 實際需要的 Service：
    - get_me 只需 get_current_user
    - get_my_identities 額外需要 UserIdentityService
    不會被迫依賴 JWTService、LoginProviderFactory 等不相關的 Service。
"""

import hashlib
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, status

from database.service import ApiKeyService, UserIdentityService
from routes.dependencies import get_api_key_service, get_current_user, get_identity_service
from routes.schemas import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyListItemResponse,
    IdentityResponse,
    MessageResponse,
    UserResponse,
)

# ──────────────────────────────────────────────
# Router 定義 (S: 僅作為 User 端點的命名空間)
# ──────────────────────────────────────────────
user_router = APIRouter(prefix="/users", tags=["Users"])


def _hash_api_key(raw_key: str) -> str:
    """將 API Key 轉為固定長度雜湊，資料庫僅保存雜湊值。"""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


@user_router.get(
    "/me",
    response_model=UserResponse,
    summary="取得當前使用者資料",
)
async def get_me(current_user=Depends(get_current_user)):
    """
    回傳當前已驗證使用者的基本資料。

    (D) 依賴反轉：使用者物件由 get_current_user 依賴注入，
        不自行解析 token 或查詢資料庫。
    """
    return UserResponse.model_validate(current_user)


@user_router.get(
    "/me/identities",
    response_model=list[IdentityResponse],
    summary="取得當前使用者的身份驗證來源",
)
async def get_my_identities(
    current_user=Depends(get_current_user),
    identity_svc: UserIdentityService = Depends(get_identity_service),
):
    """
    回傳當前使用者已綁定的所有身份驗證來源。

    (S) 單一職責：僅協調 UserIdentityService 查詢，不含其他邏輯。
    (I) 介面隔離：只依賴 UserIdentityService，不依賴 JWTService 等不相關的 Service。

    例如使用者可能同時綁定了 Google、Discord 和密碼登入。
    """
    identities = await identity_svc.get_all_by_user(current_user.id)
    return [IdentityResponse.model_validate(ident) for ident in identities]


@user_router.post(
    "/me/api-keys",
    response_model=ApiKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="申請 API Key（僅 Bearer）",
)
async def create_my_api_key(
    payload: ApiKeyCreateRequest,
    current_user=Depends(get_current_user),
    api_key_svc: ApiKeyService = Depends(get_api_key_service),
):
    """
    為當前使用者建立新的 API Key。

    僅接受 Bearer token 驗證（透過 get_current_user），
    建立後只回傳一次明文 API Key。
    """
    raw_api_key = f"ivr_{secrets.token_urlsafe(32)}"
    key_hash = _hash_api_key(raw_api_key)

    api_key = await api_key_svc.create_api_key(
        user_id=current_user.id,
        key_hash=key_hash,
        name=payload.name,
    )

    return ApiKeyCreateResponse(
        id=api_key.id,
        name=api_key.name,
        api_key=raw_api_key,
        is_active=api_key.is_active,
        created_at=api_key.created_at,
    )


@user_router.get(
    "/me/api-keys",
    response_model=list[ApiKeyListItemResponse],
    summary="列出當前使用者 API Keys（僅 Bearer）",
)
async def list_my_api_keys(
    current_user=Depends(get_current_user),
    api_key_svc: ApiKeyService = Depends(get_api_key_service),
):
    """
    取得當前使用者所有 API Key 的 metadata。

    安全考量：列表不回傳明文 API Key。
    """
    keys = await api_key_svc.get_all_by_user(current_user.id)
    sorted_keys = sorted(keys, key=lambda item: item.created_at, reverse=True)
    return [ApiKeyListItemResponse.model_validate(item) for item in sorted_keys]


@user_router.delete(
    "/me/api-keys/{key_id}",
    response_model=MessageResponse,
    summary="停用 API Key（僅 Bearer）",
)
async def deactivate_my_api_key(
    key_id: uuid.UUID = Path(..., description="API Key UUID"),
    current_user=Depends(get_current_user),
    api_key_svc: ApiKeyService = Depends(get_api_key_service),
):
    """停用當前使用者名下的 API Key。"""
    key_record = await api_key_svc.get_by_id(key_id)
    if key_record is None or key_record.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API Key 不存在",
        )

    if not key_record.is_active:
        return MessageResponse(message="API Key 已停用")

    await api_key_svc.deactivate(key_id)
    return MessageResponse(message="API Key 已停用")

