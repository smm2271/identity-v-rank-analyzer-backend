"""
JWT Service
===========
負責 JWT 的簽發與驗證，遵循單一職責原則。

- 使用 RS256 非對稱演算法
- 依賴 KeyManager 取得金鑰（依賴反轉）
- 支援 token_ver 撤銷機制
"""

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import jwt

from auth.jwt.key_manager import KeyManager


# ──────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────
@dataclass(frozen=True)
class TokenPayload:
    """解析後的 Token 資料"""
    uuid: uuid.UUID
    token_ver: int
    exp: datetime
    iat: datetime
    token_type: str = "access"  # 'access' 或 'refresh'


# ──────────────────────────────────────────────
# Exceptions
# ──────────────────────────────────────────────
class TokenError(Exception):
    """JWT 相關錯誤的基底類別"""


class TokenExpiredError(TokenError):
    """Token 已過期"""


class TokenInvalidError(TokenError):
    """Token 無效（簽名錯誤、格式不正確等）"""


class TokenRevokedError(TokenError):
    """Token 已被撤銷（token_ver 不一致）"""


# ──────────────────────────────────────────────
# JWT Service
# ──────────────────────────────────────────────
_ALGORITHM = "RS256"
_DEFAULT_ACCESS_EXPIRE_MINUTES = 15
_DEFAULT_REFRESH_EXPIRE_DAYS = 7


class JWTService:
    """
    JWT 簽發與驗證服務。

    依賴 KeyManager 提供金鑰（D: 依賴反轉），
    本身只負責 token 的編碼/解碼邏輯（S: 單一職責）。

    雙 Token 機制：
    - Access Token  (短期): 預設 15 分鐘，用於 API 請求驗證
    - Refresh Token (長期): 預設 7 天，用於換發新的 Access Token
    """

    def __init__(self, key_manager: KeyManager) -> None:
        self._key_manager = key_manager
        self._access_expire_minutes = int(
            os.getenv("JWT_ACCESS_EXPIRE_MINUTES", _DEFAULT_ACCESS_EXPIRE_MINUTES)
        )
        self._refresh_expire_days = int(
            os.getenv("JWT_REFRESH_EXPIRE_DAYS", _DEFAULT_REFRESH_EXPIRE_DAYS)
        )

    def create_access_token(
        self,
        user_uuid: uuid.UUID,
        token_ver: int,
        *,
        extra_claims: Dict[str, Any] | None = None,
    ) -> str:
        """
        簽發 JWT Access Token。

        Payload 格式：
        {
            "sub": { "uuid": "xxxx-xxxx", "token_ver": 3 },
            "iat": 1234567890,
            "exp": 1234567890
        }
        """
        now = datetime.now(timezone.utc)
        sub_data = json.dumps({"uuid": str(user_uuid), "token_ver": token_ver})
        payload: Dict[str, Any] = {
            "sub": sub_data,
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=self._access_expire_minutes),
        }

        if extra_claims:
            payload.update(extra_claims)

        return jwt.encode(
            payload,
            self._key_manager.private_key,
            algorithm=_ALGORITHM,
        )

    def create_refresh_token(
        self,
        user_uuid: uuid.UUID,
        token_ver: int,
    ) -> str:
        """
        簽發 JWT Refresh Token（長期）。

        用於在 Access Token 過期後換發新的 Access Token，
        不需要使用者重新登入。

        Payload 中以 "type": "refresh" 區分，防止 refresh token
        被誤用為 access token。
        """
        now = datetime.now(timezone.utc)
        sub_data = json.dumps({"uuid": str(user_uuid), "token_ver": token_ver})
        payload: Dict[str, Any] = {
            "sub": sub_data,
            "type": "refresh",
            "iat": now,
            "exp": now + timedelta(days=self._refresh_expire_days),
        }

        return jwt.encode(
            payload,
            self._key_manager.private_key,
            algorithm=_ALGORITHM,
        )

    def create_token_pair(
        self,
        user_uuid: uuid.UUID,
        token_ver: int,
        *,
        extra_claims: Dict[str, Any] | None = None,
    ) -> Dict[str, str]:
        """
        一次簽發 Access + Refresh Token 組合。

        Returns:
            {"access_token": "...", "refresh_token": "..."}
        """
        return {
            "access_token": self.create_access_token(
                user_uuid, token_ver, extra_claims=extra_claims
            ),
            "refresh_token": self.create_refresh_token(user_uuid, token_ver),
        }

    def verify_token(self, token: str) -> TokenPayload:
        """
        驗證 JWT 簽名與有效期限，回傳解析後的 payload。

        Raises:
            TokenExpiredError: Token 已過期
            TokenInvalidError: 簽名錯誤或格式不正確
        """
        try:
            payload = jwt.decode(
                token,
                self._key_manager.public_key,
                algorithms=[_ALGORITHM],
            )
        except jwt.ExpiredSignatureError:
            raise TokenExpiredError("Token 已過期")
        except jwt.InvalidTokenError as e:
            raise TokenInvalidError(f"Token 無效: {e}")

        try:
            sub = json.loads(payload.get("sub", "{}"))
        except (json.JSONDecodeError, TypeError) as e:
            raise TokenInvalidError(f"Token sub 欄位格式錯誤: {e}")

        return TokenPayload(
            uuid=uuid.UUID(sub["uuid"]),
            token_ver=sub["token_ver"],
            exp=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
            iat=datetime.fromtimestamp(payload["iat"], tz=timezone.utc),
            token_type=payload.get("type", "access"),
        )

    async def verify_and_check_revocation(
        self,
        token: str,
        user_service: Any,
    ) -> TokenPayload:
        """
        驗證 Token 並檢查是否已被撤銷。

        透過比對資料庫中使用者的 token_ver 與 JWT 中的 token_ver：
        - 若一致 → token 有效
        - 若不一致 → token 已被撤銷（使用者呼叫過 increment_token_ver）

        Args:
            token: JWT 字串
            user_service: UserService 實例（依賴反轉，不直接依賴具體類別）

        Raises:
            TokenExpiredError: Token 已過期
            TokenInvalidError: 簽名錯誤或格式不正確
            TokenRevokedError: token_ver 不一致，token 已被撤銷
        """
        payload = self.verify_token(token)

        user = await user_service.get_by_id(payload.uuid)
        if user is None:
            raise TokenInvalidError("使用者不存在")

        if user.token_ver != payload.token_ver:
            raise TokenRevokedError(
                f"Token 已被撤銷 (token_ver: {payload.token_ver} != {user.token_ver})"
            )

        return payload
