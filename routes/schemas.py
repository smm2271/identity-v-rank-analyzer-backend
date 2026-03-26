"""
Route Schemas
=============
所有路由共用的 Pydantic Request / Response 模型。

SOLID 原則：
- (S) 單一職責：本模組**僅**負責資料結構定義（序列化 / 反序列化），
  不含任何業務邏輯、資料庫操作或路由定義。
  將 Schema 從路由檔案中抽出，使路由檔案只需關心 HTTP 層邏輯。
- (O) 開放封閉：新增 API 端點時只需在此新增對應 Schema，
  不需修改既有的 Schema 定義。
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


# ══════════════════════════════════════════════════
# Auth Schemas
# ══════════════════════════════════════════════════

class OAuthAuthorizeResponse(BaseModel):
    """OAuth 授權 URL 回應"""
    authorization_url: str
    state: str


class TokenResponse(BaseModel):
    """JWT Token 回應"""
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"


class RegisterRequest(BaseModel):
    """密碼註冊請求"""
    email: EmailStr
    password: str = Field(..., min_length=8, description="密碼，至少 8 字元")
    username: Optional[str] = Field(None, max_length=50, description="使用者名稱")


class LoginRequest(BaseModel):
    """密碼登入請求"""
    identifier: str = Field(..., min_length=1, description="電子郵件或使用者名稱")
    password: str


class RefreshRequest(BaseModel):
    """Refresh Token 請求"""
    refresh_token: str


class MessageResponse(BaseModel):
    """通用訊息回應"""
    message: str


class ProvidersResponse(BaseModel):
    """可用的登入供應商列表回應"""
    oauth_providers: list[str]
    password_enabled: bool


# ══════════════════════════════════════════════════
# User Schemas
# ══════════════════════════════════════════════════

class UserResponse(BaseModel):
    """使用者資料回應"""
    id: uuid.UUID
    username: Optional[str]
    email: Optional[str]
    created_at: datetime
    token_ver: int

    model_config = {"from_attributes": True}


class IdentityResponse(BaseModel):
    """身份驗證來源回應"""
    id: uuid.UUID
    provider: str
    provider_key: str

    model_config = {"from_attributes": True}
