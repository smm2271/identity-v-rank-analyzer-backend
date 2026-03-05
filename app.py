"""
Application Entry Point — Composition Root
============================================
FastAPI 應用程式的進入點。

═══════════════════════════════════════════════════
SOLID 原則對應
═══════════════════════════════════════════════════

(D) 依賴反轉 — Composition Root 模式
    本檔案是整個應用程式的「組合根 (Composition Root)」，
    **唯一**負責建構所有具體 Service 實例，並透過 init_dependencies()
    注入到路由層。此後路由層只透過 dependencies.py 的抽象 getter 取用，
    完全不知道 Service 如何被建構。

(S) 單一職責
    app.py 的職責是「應用程式組裝與啟動」：
    1. 載入環境變數
    2. 建構所有 Service（具體實例）
    3. 注入依賴到路由模組
    4. 註冊路由到 FastAPI app
    不包含任何業務邏輯或路由定義。

(O) 開放封閉
    新增路由模組只需：
    1. 在 routes/ 下建立新檔案
    2. 在此 app.include_router() 註冊
    既有的路由模組不需修改。
"""

import dotenv
dotenv.load_dotenv()  # 統一在啟動時載入 .env 環境變數

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from auth.jwt.key_manager import KeyManager
from auth.jwt.jwt_service import JWTService
from auth.login_interface import (
    LoginProviderFactory,
    GoogleOAuthProvider,
    DiscordOAuthProvider,
    PasswordLoginProvider,
)
from database.database import AsyncSessionLocal
from database.service import (
    ApiKeyService,
    GameMatchService,
    UserService,
    UserIdentityService,
    UserLoginLogService,
)
from routes.dependencies import init_dependencies
from routes.auth_routes import auth_router
from routes.user_routes import user_router
from routes.match import router as match_router

app = FastAPI(title="Identity V Rank Analyzer API")

# ══════════════════════════════════════════════════
# 建構所有具體 Service（Composition Root）
# ══════════════════════════════════════════════════
# (D) 依賴反轉：所有具體的 Service 實例只在此處建構，
#     路由層透過 dependencies.py 的 getter 取用，
#     不直接 import AsyncSessionLocal 或建構 Service。
# ══════════════════════════════════════════════════

user_service = UserService(AsyncSessionLocal)
identity_service = UserIdentityService(AsyncSessionLocal)
login_log_service = UserLoginLogService(AsyncSessionLocal)
api_key_service = ApiKeyService(AsyncSessionLocal)
match_service = GameMatchService(AsyncSessionLocal)

key_manager = KeyManager()
jwt_service = JWTService(key_manager)

# ── 初始化登入供應商工廠 ────────────────────────
# (O) 開放封閉：新增 OAuth 供應商只需 factory.register()，
#     不需修改路由程式碼。
login_factory = LoginProviderFactory()
login_factory.register(GoogleOAuthProvider())
login_factory.register(DiscordOAuthProvider())
login_factory.register(PasswordLoginProvider(identity_lookup=identity_service))

# ══════════════════════════════════════════════════
# 注入依賴（統一由 dependencies.py 管理）
# ══════════════════════════════════════════════════
# (D) 依賴反轉：一次性將所有 Service 注入到集中的 DI 容器，
#     所有路由模組共用同一個入口點，避免分散的 init_*() 呼叫。
# ══════════════════════════════════════════════════

init_dependencies(
    user_service=user_service,
    identity_service=identity_service,
    login_log_service=login_log_service,
    jwt_service=jwt_service,
    login_factory=login_factory,
    api_key_service=api_key_service,
    match_service=match_service,
)

# ── 路由註冊 ──────────────────────────────────
# (S) 單一職責：每個 Router 負責一個功能域
#   - auth_router:  認證相關 (/auth/*)
#   - user_router:  使用者資訊 (/users/*)
#   - match_router: 對戰紀錄 (/api/v1/matches/*)
app.include_router(auth_router)
app.include_router(user_router)
app.include_router(match_router, prefix="/api/v1")


@app.get("/")
async def read_root():
    return {"Hello": "World"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9999)
    