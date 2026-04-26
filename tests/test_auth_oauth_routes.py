from unittest.mock import AsyncMock

import pytest

from auth.login_interface.dto import OAuthAuthorizationUrl, OAuthTokens, OAuthUserInfo
from auth.login_interface import GoogleOAuthProvider


@pytest.mark.asyncio
async def test_get_providers(test_client):
    response = await test_client.get("/auth/providers")
    assert response.status_code == 200
    data = response.json()
    assert "oauth_providers" in data
    assert "google" in data["oauth_providers"]
    assert "discord" in data["oauth_providers"]


@pytest.mark.asyncio
async def test_get_authorization_url(test_client, mocker):
    # Mock Google provider's get_authorization_url
    mock_url = OAuthAuthorizationUrl(url="https://google.com/auth?state=fake", state="fake")
    mocker.patch.object(
        GoogleOAuthProvider,
        "get_authorization_url",
        new_callable=AsyncMock,
        return_value=mock_url,
    )
    
    response = await test_client.get(
        "/auth/google/authorize",
        params={"redirect_uri": "http://localhost/callback"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["authorization_url"] == "https://google.com/auth?state=fake"
    assert data["state"] == "fake"


@pytest.mark.asyncio
async def test_get_authorization_url_unsupported_provider(test_client):
    response = await test_client.get(
        "/auth/unsupported/authorize",
        params={"redirect_uri": "http://localhost/callback"}
    )
    assert response.status_code == 400
    assert "不支援的 OAuth 供應商" in response.json()["detail"]


@pytest.mark.asyncio
async def test_oauth_callback_new_user(test_client, mocker):
    # This tests the REGISTRATION_REQUIRED branch
    
    # 1. Generate valid state
    state_res = await test_client.get(
        "/auth/google/authorize",
        params={"redirect_uri": "http://localhost/callback"}
    )
    state = state_res.json()["state"]
    
    # 2. Mock exchange_code and fetch_user_info
    mocker.patch.object(
        GoogleOAuthProvider,
        "exchange_code",
        new_callable=AsyncMock,
        return_value=OAuthTokens(access_token="fake_access", refresh_token="fake_refresh"),
    )
    mocker.patch.object(
        GoogleOAuthProvider,
        "fetch_user_info",
        new_callable=AsyncMock,
        return_value=OAuthUserInfo(
            provider="google",
            provider_key="google123",
            email="newoauth@example.com",
            username="New OAuth User"
        ),
    )
    
    # 3. Call callback
    response = await test_client.get(
        "/auth/google/callback",
        params={
            "code": "fake_code",
            "state": state,
            "redirect_uri": "http://localhost/callback"
        }
    )
    
    # Assert registration is required
    assert response.status_code == 403
    data = response.json()
    assert data["detail"]["code"] == "REGISTRATION_REQUIRED"
    assert "registration_token" in data["detail"]
    
    # 4. Finalize registration
    reg_token = data["detail"]["registration_token"]
    final_res = await test_client.post(
        "/auth/oauth-finalize",
        json={
            "registration_token": reg_token,
            "username": "oauthuser",
            "terms_accepted": True
        }
    )
    assert final_res.status_code == 201
    assert "access_token" in final_res.json()


@pytest.mark.asyncio
async def test_oauth_callback_link_required(test_client, mocker):
    # First, register a user with password
    await test_client.post(
        "/auth/register",
        json={
            "username": "existuser",
            "email": "linkme@example.com",
            "password": "StrongPassword123!",
            "terms_accepted": True
        }
    )
    
    # Then OAuth with same email
    state_res = await test_client.get(
        "/auth/google/authorize",
        params={"redirect_uri": "http://localhost/callback"}
    )
    state = state_res.json()["state"]
    
    mocker.patch.object(
        GoogleOAuthProvider,
        "exchange_code",
        new_callable=AsyncMock,
        return_value=OAuthTokens(access_token="fake_access"),
    )
    mocker.patch.object(
        GoogleOAuthProvider,
        "fetch_user_info",
        new_callable=AsyncMock,
        return_value=OAuthUserInfo(
            provider="google",
            provider_key="google456",
            email="linkme@example.com",
            username="Exist User"
        ),
    )
    
    response = await test_client.get(
        "/auth/google/callback",
        params={
            "code": "fake_code",
            "state": state,
            "redirect_uri": "http://localhost/callback"
        }
    )
    
    assert response.status_code == 403
    data = response.json()
    assert data["detail"]["code"] == "LINK_REQUIRED"
    assert "link_token" in data["detail"]
    assert isinstance(data["detail"]["verification_oauth_providers"], list)
    
    # Finalize Link
    link_token = data["detail"]["link_token"]
    link_res = await test_client.post(
        "/auth/link-identity",
        json={
            "identifier": "linkme@example.com",
            "link_token": link_token,
            "password": "StrongPassword123!"
        }
    )
    assert link_res.status_code == 200
    assert "access_token" in link_res.json()
