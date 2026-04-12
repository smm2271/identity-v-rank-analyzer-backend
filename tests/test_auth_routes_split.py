from __future__ import annotations

from fastapi.routing import APIRoute

from app import app
from routes.auth_oauth_routes import register_oauth_routes
from routes.auth_password_routes import register_password_routes
from routes.auth_routes import auth_router
from routes.auth_token_routes import register_token_routes


def _auth_api_routes_from_router() -> list[APIRoute]:
    return [r for r in auth_router.routes if isinstance(r, APIRoute)]


def _auth_api_routes_from_app() -> list[APIRoute]:
    return [
        r
        for r in app.routes
        if isinstance(r, APIRoute) and r.path.startswith("/auth")
    ]


def test_auth_router_entry_registers_expected_endpoints() -> None:
    routes = _auth_api_routes_from_router()

    route_contract = {(r.path, frozenset(r.methods or set())) for r in routes}

    expected_contract = {
        ("/auth/providers", frozenset({"GET"})),
        ("/auth/{provider}/authorize", frozenset({"GET"})),
        ("/auth/{provider}/callback", frozenset({"GET"})),
        ("/auth/oauth-finalize", frozenset({"POST"})),
        ("/auth/link-identity", frozenset({"POST"})),
        ("/auth/register", frozenset({"POST"})),
        ("/auth/login", frozenset({"POST"})),
        ("/auth/refresh", frozenset({"POST"})),
        ("/auth/logout", frozenset({"POST"})),
    }

    assert route_contract == expected_contract


def test_auth_router_exposes_nine_api_routes() -> None:
    routes = _auth_api_routes_from_router()
    assert len(routes) == 9


def test_app_includes_same_auth_route_contract() -> None:
    router_contract = {
        (r.path, frozenset(r.methods or set())) for r in _auth_api_routes_from_router()
    }
    app_contract = {
        (r.path, frozenset(r.methods or set())) for r in _auth_api_routes_from_app()
    }

    assert app_contract == router_contract


def test_split_modules_export_register_functions() -> None:
    assert callable(register_oauth_routes)
    assert callable(register_password_routes)
    assert callable(register_token_routes)
