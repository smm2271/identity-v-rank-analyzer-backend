from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from auth.jwt_auth.jwt_service import (
    JWTService,
    TokenError,
    TokenExpiredError,
    TokenInvalidError,
    TokenRevokedError,
)
from database.service import RefreshTokenService, UserService
from routes.auth_shared import (
    _REFRESH_COOKIE_NAME,
    _clear_refresh_cookie,
    _issue_token_response,
)
from routes.dependencies import (
    get_jwt_service,
    get_refresh_token_service,
    get_user_service,
)
from routes.schemas import TokenResponse


def register_token_routes(auth_router: APIRouter) -> None:
    @auth_router.post(
        "/refresh",
        response_model=TokenResponse,
        summary="以 Refresh Token 換發新 Token",
    )
    async def refresh_token(
        request: Request,
        response: Response,
        jwt_svc: JWTService = Depends(get_jwt_service),
        user_svc: UserService = Depends(get_user_service),
        refresh_token_svc: RefreshTokenService = Depends(get_refresh_token_service),
    ):
        refresh_token_value = request.cookies.get(_REFRESH_COOKIE_NAME)
        if not refresh_token_value:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token 缺失，請重新登入",
            )

        try:
            payload = await jwt_svc.verify_and_check_revocation(
                refresh_token_value, user_svc
            )
        except TokenExpiredError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token 已過期，請重新登入",
            )
        except TokenRevokedError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token 已被撤銷，請重新登入",
            )
        except (TokenInvalidError, TokenError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token 無效",
            )

        if payload.token_type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="請提供 refresh token，而非 access token",
            )

        if payload.jti is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token 缺少 jti，請重新登入",
            )

        active_session = await refresh_token_svc.get_active_by_jti(payload.jti)
        if active_session is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token session 已失效，請重新登入",
            )

        user = await user_svc.get_by_id(payload.uuid)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="使用者不存在",
            )

        if active_session.user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token session 與使用者不一致",
            )

        await refresh_token_svc.revoke_by_jti(payload.jti)

        return await _issue_token_response(
            user=user,
            response=response,
            jwt_svc=jwt_svc,
            refresh_token_svc=refresh_token_svc,
        )

    @auth_router.post(
        "/logout",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="登出（僅撤銷當前 Session）",
    )
    async def logout(
        request: Request,
        response: Response,
        jwt_svc: JWTService = Depends(get_jwt_service),
        user_svc: UserService = Depends(get_user_service),
        refresh_token_svc: RefreshTokenService = Depends(get_refresh_token_service),
    ):
        refresh_token_value = request.cookies.get(_REFRESH_COOKIE_NAME)
        if refresh_token_value:
            try:
                payload = await jwt_svc.verify_and_check_revocation(refresh_token_value, user_svc)
                if payload.token_type == "refresh" and payload.jti is not None:
                    await refresh_token_svc.revoke_by_jti(payload.jti)
            except (TokenError, TokenExpiredError, TokenInvalidError, TokenRevokedError):
                pass

        _clear_refresh_cookie(response)
