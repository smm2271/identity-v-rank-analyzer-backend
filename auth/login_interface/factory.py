"""
OAuth Provider Factory
=======================
集中管理所有 OAuth2 登入供應商的註冊與取用。

遵循 SOLID 原則：
- S: Factory 僅負責供應商的註冊與實例化，不含登入業務邏輯。
- O: 新增供應商只需呼叫 register()，無須修改 Factory 本身。
- D: 回傳抽象的 OAuthLoginInterface，上層不依賴具體類別。

用法：
    factory = OAuthProviderFactory()
    factory.register("google", GoogleOAuthProvider(...))
    factory.register("discord", DiscordOAuthProvider(...))

    provider = factory.get("google")
    url_info = await provider.get_authorization_url(redirect_uri=..., state=...)
"""

from typing import Dict

from auth.login_interface.base import OAuthLoginInterface


class ProviderNotRegisteredError(Exception):
    """嘗試取用尚未註冊的供應商"""


class OAuthProviderFactory:
    """
    OAuth2 供應商工廠。

    以 provider name 為 key 註冊各供應商實例，
    消費端透過名稱取得抽象介面，無需知道具體類別。
    """

    def __init__(self) -> None:
        self._providers: Dict[str, OAuthLoginInterface] = {}

    def register(self, provider: OAuthLoginInterface) -> None:
        """
        註冊一個 OAuth2 供應商。

        Provider 名稱由 provider.get_provider_name() 決定，
        無需額外傳入字串，確保名稱一致性。

        Args:
            provider: 實作 OAuthLoginInterface 的供應商實例
        """
        name = provider.get_provider_name()
        self._providers[name] = provider

    def get(self, provider_name: str) -> OAuthLoginInterface:
        """
        根據名稱取得已註冊的供應商。

        Args:
            provider_name: 供應商名稱（如 'google', 'discord'）

        Returns:
            OAuthLoginInterface 實例

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

    def list_providers(self) -> list[str]:
        """列出所有已註冊的供應商名稱"""
        return sorted(self._providers.keys())

    def has(self, provider_name: str) -> bool:
        """檢查供應商是否已註冊"""
        return provider_name in self._providers
