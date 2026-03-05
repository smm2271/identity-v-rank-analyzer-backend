"""
Login Provider Factory
=======================
集中管理所有登入供應商（OAuth2 與密碼）的註冊與取用。

遵循 SOLID 原則：
- S: Factory 僅負責供應商的註冊與實例化，不含登入業務邏輯。
- O: 新增供應商只需呼叫 register()，無須修改 Factory 本身。
- D: 回傳抽象的 LoginProviderBase，上層不依賴具體類別。

用法：
    factory = LoginProviderFactory()
    factory.register(GoogleOAuthProvider(...))
    factory.register(DiscordOAuthProvider(...))
    factory.register(PasswordLoginProvider(identity_lookup=...))

    # 取得 OAuth 供應商
    oauth = factory.get_oauth("google")
    url_info = await oauth.get_authorization_url(redirect_uri=..., state=...)

    # 取得密碼登入供應商
    pwd = factory.get_password()
    result = await pwd.authenticate(identifier=..., password=...)
"""

from typing import Dict

from auth.login_interface.base import (
    LoginProviderBase,
    OAuthLoginInterface,
    PasswordLoginInterface,
)


class ProviderNotRegisteredError(Exception):
    """嘗試取用尚未註冊的供應商"""


class LoginProviderFactory:
    """
    登入供應商工廠。

    以 provider name 為 key 統一註冊 OAuth2 與密碼供應商，
    消費端透過名稱取得抽象介面，無需知道具體類別。

    提供型別安全的取用方法：
    - get()          → 回傳 LoginProviderBase（最寬鬆）
    - get_oauth()    → 回傳 OAuthLoginInterface（型別安全）
    - get_password() → 回傳 PasswordLoginInterface（型別安全）
    """

    def __init__(self) -> None:
        self._providers: Dict[str, LoginProviderBase] = {}

    def register(self, provider: LoginProviderBase) -> None:
        """
        註冊一個登入供應商。

        Provider 名稱由 provider.get_provider_name() 決定，
        無需額外傳入字串，確保名稱一致性。

        Args:
            provider: 實作 LoginProviderBase 的供應商實例
        """
        name = provider.get_provider_name()
        self._providers[name] = provider

    def get(self, provider_name: str) -> LoginProviderBase:
        """
        根據名稱取得已註冊的供應商（回傳基底型別）。

        Args:
            provider_name: 供應商名稱（如 'google', 'discord', 'password'）

        Returns:
            LoginProviderBase 實例

        Raises:
            ProviderNotRegisteredError: 供應商未註冊
        """
        provider = self._providers.get(provider_name)
        if provider is None:
            available = ", ".join(sorted(self._providers.keys())) or "(無)"
            raise ProviderNotRegisteredError(
                f"供應商 '{provider_name}' 尚未註冊。已註冊: {available}"
            )
        return provider

    def get_oauth(self, provider_name: str) -> OAuthLoginInterface:
        """
        取得 OAuth2 供應商（型別安全）。

        Raises:
            ProviderNotRegisteredError: 供應商未註冊
            TypeError: 該供應商不是 OAuth2 類型
        """
        provider = self.get(provider_name)
        if not isinstance(provider, OAuthLoginInterface):
            raise TypeError(
                f"供應商 '{provider_name}' 不是 OAuth2 類型 "
                f"(實際類型: {type(provider).__name__})"
            )
        return provider

    def get_password(self) -> PasswordLoginInterface:
        """
        取得密碼登入供應商（型別安全，固定名稱 'password'）。

        Raises:
            ProviderNotRegisteredError: 密碼供應商未註冊
            TypeError: 該供應商不是密碼登入類型
        """
        provider = self.get("password")
        if not isinstance(provider, PasswordLoginInterface):
            raise TypeError(
                f"'password' 供應商不是密碼登入類型 "
                f"(實際類型: {type(provider).__name__})"
            )
        return provider

    def list_providers(self) -> list[str]:
        """列出所有已註冊的供應商名稱"""
        return sorted(self._providers.keys())

    def list_oauth_providers(self) -> list[str]:
        """列出所有已註冊的 OAuth2 供應商名稱"""
        return sorted(
            name for name, p in self._providers.items()
            if isinstance(p, OAuthLoginInterface)
        )

    def has(self, provider_name: str) -> bool:
        """檢查供應商是否已註冊"""
        return provider_name in self._providers


# 為向下相容保留別名
OAuthProviderFactory = LoginProviderFactory
