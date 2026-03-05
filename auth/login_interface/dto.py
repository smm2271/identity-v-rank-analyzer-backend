"""
Login Interface Data Transfer Objects
=====================================
定義登入介面共用的資料傳輸物件。

遵循 SOLID 原則：
- S: DTO 僅負責資料結構定義，不含業務邏輯。
- O: 使用 dataclass 可被繼承擴展，不需修改原有欄位。
"""

import uuid
from dataclasses import dataclass, field
from typing import Optional


# ──────────────────────────────────────────────
# OAuth2 DTOs
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class OAuthUserInfo:
    """
    OAuth2 第三方供應商回傳的使用者資訊（標準化格式）。

    不同供應商的回傳格式不同，各 Provider 需將原始資料
    轉換成此統一格式，供上層業務邏輯使用。

    Attributes:
        provider:      供應商名稱，如 'google', 'discord'
        provider_key:  供應商端的唯一使用者 ID (對應 user_identities.provider_key)
        email:         使用者 Email（部分供應商可能不提供）
        username:      使用者顯示名稱
        avatar_url:    使用者頭像 URL
        raw_data:      原始回傳資料（供除錯或未來擴展使用）
    """
    provider: str
    provider_key: str
    email: Optional[str] = None
    username: Optional[str] = None
    avatar_url: Optional[str] = None
    raw_data: dict = field(default_factory=dict)


@dataclass(frozen=True)
class OAuthTokens:
    """
    OAuth2 Token 交換後取得的 Token 組合。

    Attributes:
        access_token:  短期存取令牌
        refresh_token: 長期刷新令牌（部分供應商可能不提供）
        token_type:    令牌類型，通常為 'Bearer'
        expires_in:    存取令牌有效秒數
        scope:         授權範圍
    """
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: Optional[int] = None
    scope: Optional[str] = None


@dataclass(frozen=True)
class OAuthAuthorizationUrl:
    """
    OAuth2 授權 URL 資訊。

    Attributes:
        url:   完整的授權重導向 URL
        state: 防 CSRF 的 state 參數（由呼叫端保存並於回呼時比對）
    """
    url: str
    state: str


# ──────────────────────────────────────────────
# Password Login DTOs
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class PasswordAuthResult:
    """
    密碼驗證結果。

    authenticate() 成功後回傳此物件，包含足夠的資訊
    讓上層查詢或建立使用者。

    對應 model.dbml 的 user_identities 表：
    - provider      = 'password'
    - provider_key  = identifier（即 email）
    - secret_hash   = 密碼的 bcrypt 雜湊值（已驗證通過）

    Attributes:
        provider:      固定為 'password'
        provider_key:  使用者登入識別（email）
        user_id:       已存在的使用者 UUID（驗證成功時才有值）
        email:         使用者 Email
        username:      使用者名稱
    """
    provider: str
    provider_key: str
    user_id: Optional[uuid.UUID] = None
    email: Optional[str] = None
    username: Optional[str] = None
