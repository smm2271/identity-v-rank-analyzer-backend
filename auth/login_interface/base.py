"""
Login Interface — Abstract Base
================================
定義所有登入供應商必須實作的抽象介面。

架構分層：
- LoginProviderBase:       所有登入供應商的最小公約數（僅 get_provider_name）
- OAuthLoginInterface:     OAuth2 供應商專用介面（Authorization Code Flow）
- PasswordLoginInterface:  密碼登入專用介面（帳號 + 密碼驗證）

遵循 SOLID 原則：
- S: 介面只定義「登入流程」的契約，不包含業務邏輯。
- O: 新增供應商只需繼承對應介面並實作方法，無須修改現有程式碼。
- L: 同一介面的所有實作可互相替換，上層程式碼無需感知具體類別。
- I: OAuth 與 Password 拆分為獨立介面，消費端只依賴所需的方法。
     密碼登入不需實作 get_authorization_url / exchange_code 等 OAuth 方法；
     OAuth 登入不需實作 authenticate / hash_password 等密碼方法。
- D: 上層邏輯依賴抽象介面，不依賴具體的 Google/Discord/Password 實作。

對應 model.dbml 的 user_identities 表：
- provider      → get_provider_name() 回傳值 ('google', 'discord', 'password')
- provider_key  → OAuth: 供應商的使用者 ID / Password: 使用者的 email
- secret_hash   → OAuth: refresh_token 雜湊（可選）/ Password: bcrypt 密碼雜湊
"""

from abc import ABC, abstractmethod
from typing import Optional

from auth.login_interface.dto import (
    OAuthAuthorizationUrl,
    OAuthTokens,
    OAuthUserInfo,
    PasswordAuthResult,
)


# ──────────────────────────────────────────────
# Login Provider Base (所有登入方式的共用基底)
# ──────────────────────────────────────────────
class LoginProviderBase(ABC):
    """
    所有登入供應商的共用基底介面。

    無論是 OAuth2 或密碼登入，都必須實作此方法。
    Factory 透過 get_provider_name() 進行註冊與查詢。
    """

    @abstractmethod
    def get_provider_name(self) -> str:
        """
        回傳供應商名稱（對應 user_identities.provider 欄位）。

        Returns:
            供應商識別字串，如 'google', 'discord', 'password'
        """
        ...


# ──────────────────────────────────────────────
# OAuth2 Login Interface
# ──────────────────────────────────────────────
class OAuthLoginInterface(LoginProviderBase):
    """
    OAuth2 登入供應商的抽象介面。

    任何新的 OAuth2 供應商（如 Google、Discord、GitHub 等）
    都必須繼承此類別並實作所有抽象方法。

    典型 OAuth2 Authorization Code Flow：
    1. get_authorization_url() → 產生授權 URL，引導使用者前往供應商授權頁面
    2. exchange_code()         → 使用者授權後，以 authorization code 換取 tokens
    3. fetch_user_info()       → 以 access_token 取得使用者資訊
    """

    @abstractmethod
    async def get_authorization_url(
        self,
        *,
        redirect_uri: str,
        state: str,
    ) -> OAuthAuthorizationUrl:
        """
        產生 OAuth2 授權 URL。

        Args:
            redirect_uri: 授權完成後的回呼 URL
            state:        防 CSRF 的隨機字串，由呼叫端產生並保存

        Returns:
            OAuthAuthorizationUrl 包含完整 URL 與 state
        """
        ...

    @abstractmethod
    async def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
    ) -> OAuthTokens:
        """
        以 authorization code 向供應商交換 access token。

        Args:
            code:         使用者授權後，供應商回傳的 authorization code
            redirect_uri: 必須與 get_authorization_url 時使用的一致

        Returns:
            OAuthTokens 包含 access_token 及可選的 refresh_token

        Raises:
            OAuthError: 交換失敗（code 無效、過期等）
        """
        ...

    @abstractmethod
    async def fetch_user_info(self, *, access_token: str) -> OAuthUserInfo:
        """
        以 access_token 向供應商取得使用者資訊。

        回傳的 OAuthUserInfo 會被上層用於：
        - 查詢 user_identities 表（provider + provider_key）
        - 若使用者不存在，建立新的 User + UserIdentity

        Args:
            access_token: 由 exchange_code 取得的存取令牌

        Returns:
            OAuthUserInfo 標準化的使用者資訊

        Raises:
            OAuthError: 取得資訊失敗（token 無效等）
        """
        ...

    @abstractmethod
    async def revoke_token(self, *, token: str) -> bool:
        """
        撤銷指定的 OAuth token。

        並非所有供應商都支援此操作；若不支援，實作中應回傳 False。

        Args:
            token: 要撤銷的 access_token 或 refresh_token

        Returns:
            是否成功撤銷
        """
        ...


# ──────────────────────────────────────────────
# Password Login Interface
# ──────────────────────────────────────────────
class PasswordLoginInterface(LoginProviderBase):
    """
    密碼登入供應商的抽象介面。

    對應 model.dbml 的 user_identities 表：
    - provider      = 'password'
    - provider_key  = 使用者的 email（作為唯一識別）
    - secret_hash   = bcrypt 密碼雜湊

    實作此介面的類別負責：
    1. authenticate()    → 驗證帳號密碼
    2. hash_password()   → 將明文密碼轉為安全雜湊
    3. verify_password() → 比對明文密碼與雜湊值
    4. validate_password_strength() → 檢查密碼強度是否符合政策
    """

    @abstractmethod
    async def authenticate(
        self,
        *,
        identifier: str,
        password: str,
    ) -> PasswordAuthResult:
        """
        驗證使用者帳號密碼。

        Args:
            identifier: 登入識別（email）
            password:   明文密碼

        Returns:
            PasswordAuthResult 包含驗證結果與使用者資訊

        Raises:
            PasswordAuthError: 驗證失敗
        """
        ...

    @abstractmethod
    def hash_password(self, password: str) -> str:
        """
        將明文密碼轉為安全雜湊值。

        用於註冊或修改密碼時，產生 secret_hash 存入
        user_identities.secret_hash 欄位。

        Args:
            password: 明文密碼

        Returns:
            bcrypt 雜湊字串
        """
        ...

    @abstractmethod
    def verify_password(self, password: str, hashed: str) -> bool:
        """
        比對明文密碼與儲存的雜湊值。

        Args:
            password: 使用者輸入的明文密碼
            hashed:   資料庫中儲存的 bcrypt 雜湊值

        Returns:
            密碼是否正確
        """
        ...

    @abstractmethod
    def validate_password_strength(self, password: str) -> Optional[str]:
        """
        檢查密碼是否符合強度要求。

        Args:
            password: 待檢查的明文密碼

        Returns:
            None 表示通過；否則回傳不符合原因的說明字串
        """
        ...


# ──────────────────────────────────────────────
# Errors
# ──────────────────────────────────────────────
class OAuthError(Exception):
    """OAuth2 流程中發生的錯誤基底類別"""

    def __init__(self, provider: str, message: str) -> None:
        self.provider = provider
        self.message = message
        super().__init__(f"[{provider}] {message}")


class OAuthCodeExchangeError(OAuthError):
    """Authorization Code 交換失敗"""


class OAuthUserInfoError(OAuthError):
    """取得使用者資訊失敗"""


class OAuthTokenRevokeError(OAuthError):
    """Token 撤銷失敗"""
