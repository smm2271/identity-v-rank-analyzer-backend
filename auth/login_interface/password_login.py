"""
Password Login Provider
========================
實作密碼登入的驗證邏輯。

對應 model.dbml 的 user_identities 表：
- provider      = 'password'
- provider_key  = 使用者的 email（唯一識別）
- secret_hash   = bcrypt 密碼雜湊值

遵循 SOLID 原則：
- S: 僅負責密碼的雜湊、驗證與強度檢查，不含 DB 操作。
- L: 可替換為任何 PasswordLoginInterface 的實作（如改用 argon2）。
- D: 依賴 UserIdentityService 抽象查詢身份，由外部注入。

密碼政策（預設）：
- 最少 8 字元
- 至少包含一個大寫字母
- 至少包含一個小寫字母
- 至少包含一個數字
"""

import re
from typing import Any, Optional, Protocol, runtime_checkable

import bcrypt

from auth.login_interface.base import PasswordLoginInterface
from auth.login_interface.dto import PasswordAuthResult


# ──────────────────────────────────────────────
# Dependency Protocol (依賴反轉)
# ──────────────────────────────────────────────
@runtime_checkable
class IdentityLookup(Protocol):
    """
    查詢 user_identities 的最小介面。

    PasswordLoginProvider 僅依賴此 Protocol，
    不直接依賴 UserIdentityService 具體類別。
    """

    async def get_by_provider(
        self, provider: str, provider_key: str
    ) -> Any: ...


# ──────────────────────────────────────────────
# Password Policy
# ──────────────────────────────────────────────
_MIN_LENGTH = 8
_REQUIRE_UPPERCASE = True
_REQUIRE_LOWERCASE = True
_REQUIRE_DIGIT = True


# ──────────────────────────────────────────────
# Errors
# ──────────────────────────────────────────────
class PasswordAuthError(Exception):
    """密碼驗證相關錯誤的基底類別"""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"[password] {message}")


class InvalidCredentialsError(PasswordAuthError):
    """帳號或密碼錯誤"""


class IdentityNotFoundError(PasswordAuthError):
    """找不到對應的密碼身份"""


class WeakPasswordError(PasswordAuthError):
    """密碼強度不足"""


# ──────────────────────────────────────────────
# Password Login Provider
# ──────────────────────────────────────────────
class PasswordLoginProvider(PasswordLoginInterface):
    """
    密碼登入供應商實作。

    使用 bcrypt 進行密碼雜湊與驗證，支援：
    - 驗證帳號密碼（查詢 user_identities + 比對 bcrypt hash）
    - 產生密碼雜湊（用於註冊或修改密碼）
    - 比對密碼與雜湊
    - 檢查密碼強度

    依賴 IdentityLookup（Protocol）查詢身份，
    實務上注入 UserIdentityService 即可。

    用法：
        identity_service = UserIdentityService(session_factory)
        provider = PasswordLoginProvider(identity_lookup=identity_service)

        # 驗證登入
        result = await provider.authenticate(
            identifier="user@example.com",
            password="P@ssw0rd123",
        )

        # 註冊時產生雜湊
        hashed = provider.hash_password("P@ssw0rd123")
    """

    def __init__(
        self,
        *,
        identity_lookup: IdentityLookup,
        bcrypt_rounds: int = 12,
        min_length: int = _MIN_LENGTH,
        require_uppercase: bool = _REQUIRE_UPPERCASE,
        require_lowercase: bool = _REQUIRE_LOWERCASE,
        require_digit: bool = _REQUIRE_DIGIT,
    ) -> None:
        """
        Args:
            identity_lookup:   實作 IdentityLookup 的服務（通常為 UserIdentityService）
            bcrypt_rounds:     bcrypt 雜湊輪數（越高越安全但越慢，預設 12）
            min_length:        密碼最短長度
            require_uppercase: 是否要求包含大寫字母
            require_lowercase: 是否要求包含小寫字母
            require_digit:     是否要求包含數字
        """
        self._identity_lookup = identity_lookup
        self._bcrypt_rounds = bcrypt_rounds
        self._min_length = min_length
        self._require_uppercase = require_uppercase
        self._require_lowercase = require_lowercase
        self._require_digit = require_digit

    # ── Interface Implementation ─────────────────

    def get_provider_name(self) -> str:
        return "password"

    async def authenticate(
        self,
        *,
        identifier: str,
        password: str,
    ) -> PasswordAuthResult:
        """
        驗證帳號密碼。

        流程：
        1. 以 provider='password' + provider_key=identifier 查詢 user_identities
        2. 若找不到 → raise IdentityNotFoundError
        3. 比對 password 與 secret_hash
        4. 若不符 → raise InvalidCredentialsError
        5. 成功 → 回傳 PasswordAuthResult

        安全考量：
        - 不論是帳號不存在或密碼錯誤，對外應統一回傳相同錯誤訊息
          以防止帳號列舉攻擊。此處分開錯誤類別是供內部日誌使用，
          上層 controller 應統一轉為 "帳號或密碼錯誤"。
        """
        identity = await self._identity_lookup.get_by_provider(
            "password", identifier
        )

        if identity is None:
            raise IdentityNotFoundError("找不到對應的密碼登入身份")

        if not identity.secret_hash:
            raise InvalidCredentialsError("帳號未設定密碼")

        if not self.verify_password(password, identity.secret_hash):
            raise InvalidCredentialsError("密碼錯誤")

        return PasswordAuthResult(
            provider="password",
            provider_key=identifier,
            user_id=identity.user_id,
        )

    def hash_password(self, password: str) -> str:
        """
        將明文密碼轉為 bcrypt 雜湊。

        回傳的字串可直接存入 user_identities.secret_hash。
        """
        salt = bcrypt.gensalt(rounds=self._bcrypt_rounds)
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    def verify_password(self, password: str, hashed: str) -> bool:
        """比對明文密碼與 bcrypt 雜湊值。"""
        return bcrypt.checkpw(
            password.encode("utf-8"),
            hashed.encode("utf-8"),
        )

    def validate_password_strength(self, password: str) -> Optional[str]:
        """
        檢查密碼強度。

        Returns:
            None 表示通過；否則回傳不符合的原因。
        """
        if len(password) < self._min_length:
            return f"密碼長度至少需要 {self._min_length} 個字元"

        if self._require_uppercase and not re.search(r"[A-Z]", password):
            return "密碼需包含至少一個大寫字母"

        if self._require_lowercase and not re.search(r"[a-z]", password):
            return "密碼需包含至少一個小寫字母"

        if self._require_digit and not re.search(r"\d", password):
            return "密碼需包含至少一個數字"

        return None
