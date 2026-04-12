"""
Auth Routes (Router Entry)
==========================
保留既有匯入路徑 routes.auth_routes:auth_router，
實際端點依責任拆分到多個模組以提升可維護性。
"""

from fastapi import APIRouter

from routes.auth_oauth_routes import register_oauth_routes
from routes.auth_password_routes import register_password_routes
from routes.auth_token_routes import register_token_routes


auth_router = APIRouter(prefix="/auth", tags=["Auth"])

register_oauth_routes(auth_router)
register_password_routes(auth_router)
register_token_routes(auth_router)
