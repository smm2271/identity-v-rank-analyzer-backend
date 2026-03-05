"""
Google OAuth2 Login Provider
=============================
實作 Google OAuth2 Authorization Code Flow。

Google OAuth2 端點：
- 授權: https://accounts.google.com/o/oauth2/v2/auth
- Token: https://oauth2.googleapis.com/token
- 使用者資訊: https://www.googleapis.com/oauth2/v2/userinfo
- 撤銷: https://oauth2.googleapis.com/revoke

對應 model.dbml 的 user_identities 表：
- provider      = 'google'
- provider_key  = Google 回傳的使用者 ID (sub)
- secret_hash   = refresh_token 的雜湊值（可選）

遵循 SOLID 原則：
- S: 僅負責 Google OAuth2 的 HTTP 交互邏輯。
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
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
_GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

_DEFAULT_SCOPES = "openid email profile"


class GoogleOAuthProvider(OAuthLoginInterface):
    """
    Google OAuth2 登入供應商實作。

    使用 Authorization Code Flow，支援：
    - 產生授權 URL
    - 以 code 交換 tokens
    - 以 access_token 取得使用者資訊
    - 撤銷 token

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
            client_id:     Google OAuth Client ID（預設讀取環境變數 GOOGLE_CLIENT_ID）
            client_secret: Google OAuth Client Secret（預設讀取環境變數 GOOGLE_CLIENT_SECRET）
            scopes:        授權範圍
            http_client:   可注入自定義的 httpx.AsyncClient（方便測試）
        """
        self._client_id = client_id or os.getenv("GOOGLE_CLIENT_ID", "")
        self._client_secret = client_secret or os.getenv("GOOGLE_CLIENT_SECRET", "")
        self._scopes = scopes
        self._http_client = http_client

    # ── Interface Implementation ─────────────────

    def get_provider_name(self) -> str:
        return "google"

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
            "access_type": "offline",       # 請求 refresh_token
            "prompt": "consent",            # 強制顯示同意畫面以取得 refresh_token
        }
        url = f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"
        return OAuthAuthorizationUrl(url=url, state=state)

    async def exchange_code(
        self,
        *,
        code: str,
        redirect_uri: str,
    ) -> OAuthTokens:
        payload = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }

        async with self._get_client() as client:
            resp = await client.post(_GOOGLE_TOKEN_URL, data=payload)

        if resp.status_code != 200:
            raise OAuthCodeExchangeError(
                "google",
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
            resp = await client.get(_GOOGLE_USERINFO_URL, headers=headers)

        if resp.status_code != 200:
            raise OAuthUserInfoError(
                "google",
                f"取得使用者資訊失敗 (HTTP {resp.status_code}): {resp.text}",
            )

        data = resp.json()
        return OAuthUserInfo(
            provider="google",
            provider_key=data["id"],              # Google 使用者唯一 ID
            email=data.get("email"),
            username=data.get("name"),
            avatar_url=data.get("picture"),
            raw_data=data,
        )

    async def revoke_token(self, *, token: str) -> bool:
        async with self._get_client() as client:
            resp = await client.post(
                _GOOGLE_REVOKE_URL,
                params={"token": token},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if resp.status_code == 200:
            return True

        raise OAuthTokenRevokeError(
            "google",
            f"Token 撤銷失敗 (HTTP {resp.status_code}): {resp.text}",
        )

    # ── Internal Helpers ─────────────────────────

    def _get_client(self) -> httpx.AsyncClient:
        """取得 HTTP client（支援外部注入，方便 mock 測試）"""
        if self._http_client is not None:
            return self._http_client
        return httpx.AsyncClient(timeout=10.0)
