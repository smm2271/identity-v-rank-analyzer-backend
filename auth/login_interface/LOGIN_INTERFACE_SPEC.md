# Login Interface 規範文件

## 1. 概述

本模組提供可替換的 OAuth2 第三方登入介面，遵循 SOLID 原則設計。所有供應商實作統一的抽象介面 `OAuthLoginInterface`，上層程式碼僅依賴抽象，不依賴具體實作，可在不修改既有程式碼的情況下新增或替換供應商。

### 目前支援的供應商

| 供應商  | 類別名稱                | provider 名稱 |
|---------|------------------------|---------------|
| Google  | `GoogleOAuthProvider`  | `google`      |
| Discord | `DiscordOAuthProvider` | `discord`     |

---

## 2. 架構設計

### 2.1 模組結構

```
auth/login_interface/
├── __init__.py           # 模組匯出
├── base.py               # 抽象介面 OAuthLoginInterface + 錯誤類別
├── dto.py                # 資料傳輸物件 (DTO)
├── factory.py            # 供應商工廠 OAuthProviderFactory
├── google_oauth.py       # Google OAuth2 實作
├── discord_oauth.py      # Discord OAuth2 實作
└── LOGIN_INTERFACE_SPEC.md  # 本規範文件
```

### 2.2 SOLID 原則對應

| 原則 | 說明 |
|------|------|
| **S — 單一職責** | 每個檔案只負責一件事：`base.py` 定義契約、`dto.py` 定義資料結構、各 Provider 只處理該供應商的 HTTP 邏輯 |
| **O — 開放封閉** | 新增供應商只需建立新類別並繼承 `OAuthLoginInterface`，再透過 Factory 註冊即可，無須修改既有程式碼 |
| **L — 里氏替換** | 所有 Provider 皆實作相同介面，可在任何接受 `OAuthLoginInterface` 的地方互相替換 |
| **I — 介面隔離** | `OAuthLoginInterface` 僅定義 OAuth2 登入流程必要的 5 個方法，不強迫實作無關功能 |
| **D — 依賴反轉** | 上層業務邏輯依賴 `OAuthLoginInterface` 抽象，不直接依賴 `GoogleOAuthProvider` 等具體類別；HTTP client 亦可注入替換 |

### 2.3 類別關係圖

```
                    ┌─────────────────────────┐
                    │  OAuthLoginInterface    │  ← 抽象介面 (ABC)
                    │  (base.py)              │
                    └────────┬────────────────┘
                             │ 繼承
               ┌─────────────┼─────────────┐
               │                           │
  ┌────────────▼──────────┐  ┌─────────────▼─────────┐
  │ GoogleOAuthProvider   │  │ DiscordOAuthProvider   │
  │ (google_oauth.py)     │  │ (discord_oauth.py)     │
  └───────────────────────┘  └────────────────────────┘
               │                           │
               └─────────┬────────────────┘
                         │ 註冊
               ┌─────────▼────────────┐
               │ OAuthProviderFactory │  ← 供應商工廠
               │ (factory.py)         │
               └──────────────────────┘
```

---

## 3. 資料模型對應 (model.dbml)

介面設計直接對應 `user_identities` 表：

```dbml
Table user_identities {
  id uuid [pk]
  user_id uuid [ref: > User.id]
  provider varchar(20)       ← get_provider_name() 回傳值
  provider_key varchar(255)  ← OAuthUserInfo.provider_key
  secret_hash varchar(255)   ← 可儲存 refresh_token 的雜湊值
}
```

### 欄位對應

| DB 欄位        | 介面對應                                     | 說明 |
|---------------|---------------------------------------------|------|
| `provider`    | `OAuthLoginInterface.get_provider_name()`   | 供應商名稱：`'google'` / `'discord'` |
| `provider_key`| `OAuthUserInfo.provider_key`                | 供應商端的唯一使用者 ID |
| `secret_hash` | `hash(OAuthTokens.refresh_token)`           | 選擇性儲存 refresh_token 的雜湊值 |

---

## 4. 抽象介面定義

### 4.1 `OAuthLoginInterface` (ABC)

所有 OAuth2 供應商**必須實作**以下 5 個方法：

```python
class OAuthLoginInterface(ABC):

    @abstractmethod
    def get_provider_name(self) -> str:
        """回傳供應商名稱 (對應 user_identities.provider)"""

    @abstractmethod
    async def get_authorization_url(
        self, *, redirect_uri: str, state: str
    ) -> OAuthAuthorizationUrl:
        """產生 OAuth2 授權 URL"""

    @abstractmethod
    async def exchange_code(
        self, *, code: str, redirect_uri: str
    ) -> OAuthTokens:
        """以 authorization code 交換 tokens"""

    @abstractmethod
    async def fetch_user_info(self, *, access_token: str) -> OAuthUserInfo:
        """以 access_token 取得使用者資訊"""

    @abstractmethod
    async def revoke_token(self, *, token: str) -> bool:
        """撤銷 token（不支援時回傳 False）"""
```

### 4.2 DTO 定義

#### `OAuthUserInfo`
```python
@dataclass(frozen=True)
class OAuthUserInfo:
    provider: str           # 供應商名稱
    provider_key: str       # 供應商端唯一使用者 ID
    email: str | None       # 使用者 Email
    username: str | None    # 顯示名稱
    avatar_url: str | None  # 頭像 URL
    raw_data: dict          # 原始回傳資料
```

#### `OAuthTokens`
```python
@dataclass(frozen=True)
class OAuthTokens:
    access_token: str            # 存取令牌
    refresh_token: str | None    # 刷新令牌
    token_type: str              # 令牌類型 (通常為 'Bearer')
    expires_in: int | None       # 有效秒數
    scope: str | None            # 授權範圍
```

#### `OAuthAuthorizationUrl`
```python
@dataclass(frozen=True)
class OAuthAuthorizationUrl:
    url: str    # 完整授權 URL
    state: str  # CSRF state 參數
```

---

## 5. 錯誤處理

所有 OAuth 錯誤繼承自 `OAuthError`：

```
OAuthError (基底)
├── OAuthCodeExchangeError    # authorization code 交換失敗
├── OAuthUserInfoError        # 取得使用者資訊失敗
└── OAuthTokenRevokeError     # token 撤銷失敗
```

每個錯誤都攜帶 `provider` 與 `message` 屬性，方便日誌記錄與錯誤追蹤。

---

## 6. 使用方式

### 6.1 初始化與註冊

```python
from auth.login_interface import (
    OAuthProviderFactory,
    GoogleOAuthProvider,
    DiscordOAuthProvider,
)

# 建立工廠並註冊供應商
factory = OAuthProviderFactory()
factory.register(GoogleOAuthProvider())    # 自動從環境變數讀取 credentials
factory.register(DiscordOAuthProvider())

# 列出已註冊的供應商
print(factory.list_providers())  # ['discord', 'google']
```

### 6.2 OAuth2 登入流程

```python
import secrets

# Step 1: 產生授權 URL
provider = factory.get("google")
state = secrets.token_urlsafe(32)
auth_info = await provider.get_authorization_url(
    redirect_uri="https://example.com/callback/google",
    state=state,
)
# → 重導向使用者到 auth_info.url

# Step 2: 使用者授權後，以 callback 中的 code 交換 tokens
tokens = await provider.exchange_code(
    code=request.query_params["code"],
    redirect_uri="https://example.com/callback/google",
)

# Step 3: 取得使用者資訊
user_info = await provider.fetch_user_info(access_token=tokens.access_token)

# Step 4: 查詢或建立使用者 (對應 user_identities 表)
identity = await identity_service.get_by_provider(
    provider=user_info.provider,          # 'google'
    provider_key=user_info.provider_key,  # Google user ID
)

if identity is None:
    # 新使用者：建立 User + UserIdentity
    user = await user_service.create_user(
        email=user_info.email,
        username=user_info.username,
        provider=user_info.provider,
        provider_key=user_info.provider_key,
        agreed_to_terms_at=datetime.now(),
    )
else:
    # 既有使用者：直接簽發 JWT
    user = await user_service.get_by_id(identity.user_id)

# Step 5: 簽發 JWT
jwt_token = jwt_service.create_access_token(
    user_uuid=user.id,
    token_ver=user.token_ver,
)
```

### 6.3 替換供應商（里氏替換示例）

```python
# 任何接受 OAuthLoginInterface 的函式都可使用不同供應商
async def handle_oauth_callback(
    provider: OAuthLoginInterface,  # ← 依賴抽象
    code: str,
    redirect_uri: str,
):
    tokens = await provider.exchange_code(code=code, redirect_uri=redirect_uri)
    user_info = await provider.fetch_user_info(access_token=tokens.access_token)
    return user_info

# Google 和 Discord 可互相替換
google_info = await handle_oauth_callback(factory.get("google"), code, uri)
discord_info = await handle_oauth_callback(factory.get("discord"), code, uri)
```

---

## 7. 環境變數設定

| 變數名稱               | 說明                          | 必要 |
|------------------------|-------------------------------|------|
| `GOOGLE_CLIENT_ID`     | Google OAuth2 Client ID       | 是   |
| `GOOGLE_CLIENT_SECRET` | Google OAuth2 Client Secret   | 是   |
| `DISCORD_CLIENT_ID`    | Discord OAuth2 Client ID      | 是   |
| `DISCORD_CLIENT_SECRET`| Discord OAuth2 Client Secret  | 是   |

> 也可在建構 Provider 實例時直接傳入 `client_id` 和 `client_secret` 參數。

---

## 8. 新增供應商指南

若需新增其他 OAuth2 供應商（如 GitHub、Apple 等），請遵循以下步驟：

1. **建立新檔案**：`auth/login_interface/{provider_name}_oauth.py`

2. **繼承 `OAuthLoginInterface`** 並實作所有 5 個抽象方法：

```python
from auth.login_interface.base import OAuthLoginInterface

class NewProviderOAuth(OAuthLoginInterface):
    def get_provider_name(self) -> str:
        return "new_provider"

    async def get_authorization_url(self, *, redirect_uri, state): ...
    async def exchange_code(self, *, code, redirect_uri): ...
    async def fetch_user_info(self, *, access_token): ...
    async def revoke_token(self, *, token): ...
```

3. **在 `__init__.py` 中匯出** 新的 Provider 類別

4. **在 Factory 中註冊**：
```python
factory.register(NewProviderOAuth())
```

5. **無須修改任何既有程式碼**（開放封閉原則）

---

## 9. 測試指南

### 9.1 Mock HTTP Client

所有 Provider 都支援注入自定義的 `httpx.AsyncClient`，方便單元測試時 mock HTTP 回應：

```python
import httpx
from unittest.mock import AsyncMock

mock_client = httpx.AsyncClient(transport=httpx.MockTransport(...))
provider = GoogleOAuthProvider(
    client_id="test-id",
    client_secret="test-secret",
    http_client=mock_client,
)
```

### 9.2 介面一致性測試

可撰寫參數化測試確保所有 Provider 行為一致：

```python
import pytest

@pytest.mark.parametrize("provider_cls", [GoogleOAuthProvider, DiscordOAuthProvider])
async def test_provider_name_not_empty(provider_cls):
    provider = provider_cls(client_id="x", client_secret="y")
    assert provider.get_provider_name() != ""
```
