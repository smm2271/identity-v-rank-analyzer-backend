"""
Login Interface Module
======================
登入介面模組，提供可替換的登入供應商實作。

遵循 SOLID 原則中的介面隔離原則 (ISP) 與依賴反轉原則 (DIP)：
- LoginProviderBase:       所有供應商的共用基底
- OAuthLoginInterface:     OAuth2 供應商專用介面（Google、Discord）
- PasswordLoginInterface:  密碼登入專用介面
- 透過 LoginProviderFactory 集中管理，支援動態註冊與切換

目前支援的供應商：
- Google OAuth2
- Discord OAuth2
- Password (帳號密碼)

快速使用範例：
    from auth.login_interface import (
        LoginProviderFactory,
        GoogleOAuthProvider,
        DiscordOAuthProvider,
        PasswordLoginProvider,
    )

    factory = LoginProviderFactory()
    factory.register(GoogleOAuthProvider())
    factory.register(DiscordOAuthProvider())
    factory.register(PasswordLoginProvider(identity_lookup=identity_service))

    # OAuth 登入
    oauth = factory.get_oauth("google")
    auth_url = await oauth.get_authorization_url(
        redirect_uri="https://example.com/callback/google",
        state="random-csrf-token",
    )

    # 密碼登入
    pwd = factory.get_password()
    result = await pwd.authenticate(identifier="user@example.com", password="...")
"""

# Abstract interfaces & errors
from auth.login_interface.base import (
    LoginProviderBase,
    OAuthLoginInterface,
    PasswordLoginInterface,
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
    PasswordAuthResult,
)

# Concrete providers
from auth.login_interface.google_oauth import GoogleOAuthProvider
from auth.login_interface.discord_oauth import DiscordOAuthProvider
from auth.login_interface.password_login import (
    PasswordLoginProvider,
    PasswordAuthError,
    InvalidCredentialsError,
    IdentityNotFoundError,
    WeakPasswordError,
)

# Factory
from auth.login_interface.factory import (
    LoginProviderFactory,
    OAuthProviderFactory,       # 向下相容別名
    ProviderNotRegisteredError,
)

__all__ = [
    # Base Interfaces
    "LoginProviderBase",
    "OAuthLoginInterface",
    "PasswordLoginInterface",
    # DTOs
    "OAuthUserInfo",
    "OAuthTokens",
    "OAuthAuthorizationUrl",
    "PasswordAuthResult",
    # OAuth Errors
    "OAuthError",
    "OAuthCodeExchangeError",
    "OAuthUserInfoError",
    "OAuthTokenRevokeError",
    # Password Errors
    "PasswordAuthError",
    "InvalidCredentialsError",
    "IdentityNotFoundError",
    "WeakPasswordError",
    # Factory
    "LoginProviderFactory",
    "OAuthProviderFactory",
    "ProviderNotRegisteredError",
    # Concrete Providers
    "GoogleOAuthProvider",
    "DiscordOAuthProvider",
    "PasswordLoginProvider",
]
