"""
Login Interface — Abstract Base
================================
定義所有 OAuth2 登入供應商必須實作的抽象介面。

遵循 SOLID 原則：
- S: 介面只定義「登入流程」的契約，不包含業務邏輯。
- O: 新增供應商只需繼承此介面並實作方法，無須修改現有程式碼。
- L: 所有實作此介面的 Provider 可互相替換，上層程式碼無需感知具體類別。
- I: 將 OAuth2 登入流程拆分為最小必要方法，消費端只依賴所需介面。
- D: 上層邏輯依賴此抽象介面，不依賴具體的 Google/Discord 實作。

對應 model.dbml：
- user_identities.provider     → get_provider_name() 回傳值
- user_identities.provider_key → OAuthUserInfo.provider_key
- user_identities.secret_hash  → 可選擇性儲存 refresh_token 的雜湊值
"""

from abc import ABC, abstractmethod

from auth.login_interface.dto import OAuthAuthorizationUrl, OAuthTokens, OAuthUserInfo


class OAuthLoginInterface(ABC):
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
    def get_provider_name(self) -> str:
        """
        回傳供應商名稱（對應 user_identities.provider 欄位）。

        Returns:
            供應商識別字串，如 'google', 'discord'
        """
        ...

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
