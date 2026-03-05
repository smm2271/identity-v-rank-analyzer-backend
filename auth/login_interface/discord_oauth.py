"""
Discord OAuth2 Login Provider
==============================
實作 Discord OAuth2 Authorization Code Flow。

Discord OAuth2 端點：
- 授權: https://discord.com/oauth2/authorize
- Token: https://discord.com/api/oauth2/token
- 使用者資訊: https://discord.com/api/users/@me
- 撤銷: https://discord.com/api/oauth2/token/revoke

對應 model.dbml 的 user_identities 表：
- provider      = 'discord'
- provider_key  = Discord 回傳的使用者 ID (snowflake)
- secret_hash   = refresh_token 的雜湊值（可選）

遵循 SOLID 原則：
- S: 僅負責 Discord OAuth2 的 HTTP 交互邏輯。
- L: 可替換為任何 OAuthLoginInterface 的實作。
- D: 依賴 httpx.AsyncClient 等抽象，可被注入替換。
"""

import os
from urllib.parse import urlencode

import httpx

from auth.login_interface.base import (
    OAuthCodeExchangeError,
    OAuthLoginInterface,
    OAuthTokenRevokeError,
    OAuthUserInfoError,
)
from auth.login_interface.dto import OAuthAuthorizationUrl, OAuthTokens, OAuthUserInfo

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────
_DISCORD_AUTH_URL = "https://discord.com/oauth2/authorize"
_DISCORD_TOKEN_URL = "https://discord.com/api/oauth2/token"
_DISCORD_USERINFO_URL = "https://discord.com/api/users/@me"
_DISCORD_REVOKE_URL = "https://discord.com/api/oauth2/token/revoke"

_DEFAULT_SCOPES = "identify email"


class DiscordOAuthProvider(OAuthLoginInterface):
    """
    Discord OAuth2 登入供應商實作。

    使用 Authorization Code Flow，支援：
    - 產生授權 URL
    - 以 code 交換 tokens
    - 以 access_token 取得使用者資訊
    - 撤銷 token

    Discord 頭像 URL 格式：
    https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png

    所有 HTTP 請求使用 httpx.AsyncClient 非同步發送。
    """

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        *,
        scopes: str = _DEFAULT_SCOPES,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """
        Args:
            client_id:     Discord OAuth Client ID（預設讀取環境變數 DISCORD_CLIENT_ID）
            client_secret: Discord OAuth Client Secret（預設讀取環境變數 DISCORD_CLIENT_SECRET）
            scopes:        授權範圍（Discord 以空格分隔）
            http_client:   可注入自定義的 httpx.AsyncClient（方便測試）
        """
        self._client_id = client_id or os.getenv("DISCORD_CLIENT_ID", "")
        self._client_secret = client_secret or os.getenv("DISCORD_CLIENT_SECRET", "")
        self._scopes = scopes
        self._http_client = http_client

    # ── Interface Implementation ─────────────────

    def get_provider_name(self) -> str:
        return "discord"

    async def get_authorization_url(
        self,
        *,
        redirect_uri: str,
        state: str,
    ) -> OAuthAuthorizationUrl:
        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self._scopes,
            "state": state,
            "prompt": "consent",
        }
        url = f"{_DISCORD_AUTH_URL}?{urlencode(params)}"
        return OAuthAuthorizationUrl(url=url, state=state)

    async def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
    ) -> OAuthTokens:
        # Discord 要求 Token 端點使用 application/x-www-form-urlencoded
        payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        async with self._get_client() as client:
            resp = await client.post(_DISCORD_TOKEN_URL, data=payload, headers=headers)

        if resp.status_code != 200:
            raise OAuthCodeExchangeError(
                "discord",
                f"Token 交換失敗 (HTTP {resp.status_code}): {resp.text}",
            )

        data = resp.json()
        return OAuthTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            token_type=data.get("token_type", "Bearer"),
            expires_in=data.get("expires_in"),
            scope=data.get("scope"),
        )

    async def fetch_user_info(self, *, access_token: str) -> OAuthUserInfo:
        headers = {"Authorization": f"Bearer {access_token}"}

        async with self._get_client() as client:
            resp = await client.get(_DISCORD_USERINFO_URL, headers=headers)

        if resp.status_code != 200:
            raise OAuthUserInfoError(
                "discord",
                f"取得使用者資訊失敗 (HTTP {resp.status_code}): {resp.text}",
            )

        data = resp.json()

        # 組合 Discord 頭像 URL
        avatar_url = None
        if data.get("avatar"):
            avatar_url = (
                f"https://cdn.discordapp.com/avatars/{data['id']}/{data['avatar']}.png"
            )

        # Discord 用戶名: 新版使用 global_name / username; 舊版使用 username#discriminator
        display_name = data.get("global_name") or data.get("username")

        return OAuthUserInfo(
            provider="discord",
            provider_key=data["id"],              # Discord snowflake ID
            email=data.get("email"),
            username=display_name,
            avatar_url=avatar_url,
            raw_data=data,
        )

    async def revoke_token(self, *, token: str) -> bool:
        # Discord 撤銷端點需要 client credentials
        payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "token": token,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        async with self._get_client() as client:
            resp = await client.post(_DISCORD_REVOKE_URL, data=payload, headers=headers)

        if resp.status_code == 200:
            return True

        raise OAuthTokenRevokeError(
            "discord",
            f"Token 撤銷失敗 (HTTP {resp.status_code}): {resp.text}",
        )

    # ── Internal Helpers ─────────────────────────

    def _get_client(self) -> httpx.AsyncClient:
        """取得 HTTP client（支援外部注入，方便 mock 測試）"""
        if self._http_client is not None:
            return self._http_client
        return httpx.AsyncClient(timeout=10.0)
