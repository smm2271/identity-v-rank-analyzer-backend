import base64
import hashlib
import hmac
import json
import os
import secrets
import time

from fastapi import HTTPException, Response, status

from auth.jwt_auth.jwt_service import JWTService
from database.service import RefreshTokenService, UserIdentityService
from routes.schemas import AuthUserBasic, TokenResponse


_STATE_SECRET = os.getenv("OAUTH_STATE_SECRET", secrets.token_urlsafe(32))
_OAUTH_FLOW_SECRET = os.getenv("OAUTH_FLOW_SECRET", secrets.token_urlsafe(32))
_STATE_MAX_AGE_SECONDS = 600
_OAUTH_FLOW_MAX_AGE_SECONDS = 1800
_REFRESH_COOKIE_NAME = "refresh_token"
_REFRESH_COOKIE_PATH = os.getenv("JWT_REFRESH_COOKIE_PATH", "/api/auth")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    cleaned = raw.split("#", 1)[0].strip()
    if not cleaned:
        return default
    return int(cleaned)


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    max_age = _env_int("JWT_REFRESH_EXPIRE_DAYS", 7) * 24 * 60 * 60
    response.set_cookie(
        key=_REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        path=_REFRESH_COOKIE_PATH,
        max_age=max_age,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=_REFRESH_COOKIE_NAME,
        path=_REFRESH_COOKIE_PATH,
    )


def _build_token_response(
    *,
    user,
    access_token: str,
) -> TokenResponse:
    return TokenResponse(
        access_token=access_token,
        user=AuthUserBasic(
            id=user.id,
            username=user.username,
            email=user.email,
        ),
    )


async def _issue_token_response(
    *,
    user,
    response: Response,
    jwt_svc: JWTService,
    refresh_token_svc: RefreshTokenService,
) -> TokenResponse:
    token_pair = jwt_svc.create_token_pair(
        user_uuid=user.id,
        token_ver=user.token_ver,
        user_name=user.username or "",
    )
    refresh_payload = jwt_svc.verify_token(token_pair["refresh_token"])
    if refresh_payload.jti is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Refresh token 缺少 jti，無法建立 session",
        )

    expires_at = refresh_payload.exp.replace(tzinfo=None)
    await refresh_token_svc.create_refresh_token(
        user_id=user.id,
        jti=refresh_payload.jti,
        expires_at=expires_at,
    )

    _set_refresh_cookie(response, token_pair["refresh_token"])
    return _build_token_response(user=user, access_token=token_pair["access_token"])


async def _link_identity_after_oauth_verification(
    *,
    link_token: str,
    user,
    verified_provider: str,
    verified_provider_key: str,
    identity_svc: UserIdentityService,
) -> None:
    pending = _verify_oauth_flow_token(link_token, "link")
    if pending is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="關聯暫存資料已失效或無效，請重新登入",
        )

    if not user.email or user.email != pending.get("email"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="驗證帳號與待關聯 Email 不一致",
        )

    if (
        pending["provider"] == verified_provider
        and pending["provider_key"] == verified_provider_key
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="請使用原本已綁定的第三方帳號進行驗證",
        )

    existing_identity = await identity_svc.get_by_provider(
        pending["provider"],
        pending["provider_key"],
    )
    if existing_identity is not None:
        if existing_identity.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="此 OAuth 身分已被其他帳號綁定",
            )
        return

    await identity_svc.create_identity(
        user_id=user.id,
        provider=pending["provider"],
        provider_key=pending["provider_key"],
        secret_hash=pending.get("secret_hash"),
    )


def _generate_signed_state() -> str:
    nonce = secrets.token_urlsafe(16)
    timestamp = str(int(time.time()))
    message = f"{nonce}:{timestamp}"
    signature = hmac.new(
        _STATE_SECRET.encode(), message.encode(), hashlib.sha256
    ).hexdigest()
    return f"{nonce}:{timestamp}:{signature}"


def _verify_signed_state(state: str) -> bool:
    try:
        parts = state.split(":")
        if len(parts) != 3:
            return False
        nonce, timestamp, signature = parts
        if int(time.time()) - int(timestamp) > _STATE_MAX_AGE_SECONDS:
            return False
        message = f"{nonce}:{timestamp}"
        expected = hmac.new(
            _STATE_SECRET.encode(), message.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature, expected)
    except Exception:
        return False


def _sign_oauth_flow_payload(payload: dict[str, object]) -> str:
    message = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded_payload = base64.urlsafe_b64encode(message).decode("ascii").rstrip("=")
    signature = hmac.new(
        _OAUTH_FLOW_SECRET.encode(), encoded_payload.encode("ascii"), hashlib.sha256
    ).hexdigest()
    return f"{encoded_payload}.{signature}"


def _verify_oauth_flow_token(token: str, expected_kind: str) -> dict[str, str] | None:
    try:
        payload_part, signature = token.rsplit(".", 1)
    except ValueError:
        return None

    expected_signature = hmac.new(
        _OAUTH_FLOW_SECRET.encode(), payload_part.encode("ascii"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        return None

    padding = "=" * (-len(payload_part) % 4)
    try:
        raw_payload = base64.urlsafe_b64decode((payload_part + padding).encode("ascii"))
        payload = json.loads(raw_payload.decode("utf-8"))
    except Exception:
        return None

    if not isinstance(payload, dict):
        return None

    kind = payload.get("kind")
    expires_at = payload.get("exp")
    if kind != expected_kind:
        return None
    try:
        expires_at_int = int(expires_at)
    except (TypeError, ValueError):
        return None

    if int(time.time()) > expires_at_int:
        return None

    return {key: str(value) for key, value in payload.items() if value is not None}


def _build_oauth_flow_token(
    *,
    kind: str,
    provider: str,
    provider_key: str,
    email: str,
    username: str | None,
    secret_hash: str | None,
) -> str:
    payload: dict[str, object] = {
        "kind": kind,
        "provider": provider,
        "provider_key": provider_key,
        "email": email,
        "exp": int(time.time()) + _OAUTH_FLOW_MAX_AGE_SECONDS,
    }
    if username is not None:
        payload["username"] = username
    if secret_hash is not None:
        payload["secret_hash"] = secret_hash

    return _sign_oauth_flow_payload(payload)
