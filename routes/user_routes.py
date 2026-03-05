"""
User Routes
===========
使用者資訊相關的 API 路由。

═══════════════════════════════════════════════════
SOLID 原則對應
═══════════════════════════════════════════════════

(S) 單一職責
    本模組**僅**負責「已登入使用者」的資訊查詢端點：
    - GET /users/me             — 取得當前使用者資料
    - GET /users/me/identities  — 取得當前使用者的所有身份驗證來源
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

from fastapi import APIRouter, Depends

from database.service import UserIdentityService
from routes.dependencies import get_current_user, get_identity_service
from routes.schemas import IdentityResponse, UserResponse

# ──────────────────────────────────────────────
# Router 定義 (S: 僅作為 User 端點的命名空間)
# ──────────────────────────────────────────────
user_router = APIRouter(prefix="/users", tags=["Users"])


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

