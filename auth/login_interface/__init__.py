"""
Login Interface Module
======================
OAuth2 登入介面模組，提供可替換的第三方登入供應商實作。

遵循 SOLID 原則中的介面隔離原則 (ISP) 與依賴反轉原則 (DIP)：
- 所有供應商實作統一的 OAuthLoginInterface 抽象介面
- 上層程式碼只依賴抽象介面，不依賴具體實作
- 透過 OAuthProviderFactory 集中管理，支援動態註冊與切換

目前支援的供應商：
- Google OAuth2
- Discord OAuth2

快速使用範例：
    from auth.login_interface import (
        OAuthProviderFactory,
        GoogleOAuthProvider,
        DiscordOAuthProvider,
    )

    factory = OAuthProviderFactory()
    factory.register(GoogleOAuthProvider())
    factory.register(DiscordOAuthProvider())

    provider = factory.get("google")
    auth_url = await provider.get_authorization_url(
        redirect_uri="https://example.com/callback/google",
        state="random-csrf-token",
    )
"""

# Abstract interface & errors
from auth.login_interface.base import (
    OAuthLoginInterface,
    OAuthError,
    OAuthCodeExchangeError,
    OAuthUserInfoError,
    OAuthTokenRevokeError,
)

# Data transfer objects
from auth.login_interface.dto import (
    OAuthUserInfo,
    OAuthTokens,
    OAuthAuthorizationUrl,
)

# Concrete providers
from auth.login_interface.google_oauth import GoogleOAuthProvider
from auth.login_interface.discord_oauth import DiscordOAuthProvider

# Factory
from auth.login_interface.factory import OAuthProviderFactory, ProviderNotRegisteredError

__all__ = [
    # Interface
    "OAuthLoginInterface",
    # DTOs
    "OAuthUserInfo",
    "OAuthTokens",
    "OAuthAuthorizationUrl",
    # Errors
    "OAuthError",
    "OAuthCodeExchangeError",
    "OAuthUserInfoError",
    "OAuthTokenRevokeError",
    "ProviderNotRegisteredError",
    # Providers
    "GoogleOAuthProvider",
    "DiscordOAuthProvider",
    # Factory
    "OAuthProviderFactory",
]
