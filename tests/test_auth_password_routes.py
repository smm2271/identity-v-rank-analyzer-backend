import pytest

@pytest.mark.asyncio
async def test_register_success(test_client):
    response = await test_client.post(
        "/auth/register",
        json={
            "username": "newuser",
            "email": "new@example.com",
            "password": "StrongPassword123!",
            "terms_accepted": True
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "Bearer"
    # Check if refresh token cookie is set
    cookies = response.cookies
    assert "refresh_token" in cookies


@pytest.mark.asyncio
async def test_register_weak_password(test_client):
    response = await test_client.post(
        "/auth/register",
        json={
            "username": "newuser",
            "email": "new2@example.com",
            "password": "weak",
            "terms_accepted": True
        }
    )
    assert response.status_code == 422
    data = response.json()
    assert any("String should have at least 8 characters" in str(e) for e in data["detail"])


@pytest.mark.asyncio
async def test_register_duplicate_email(test_client):
    # First registration
    await test_client.post(
        "/auth/register",
        json={
            "username": "user1",
            "email": "dup@example.com",
            "password": "StrongPassword123!",
            "terms_accepted": True
        }
    )
    
    # Second registration with same email
    response = await test_client.post(
        "/auth/register",
        json={
            "username": "user2",
            "email": "dup@example.com",
            "password": "StrongPassword123!",
            "terms_accepted": True
        }
    )
    assert response.status_code == 409
    assert "已被註冊" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_success(test_client):
    # Register first
    await test_client.post(
        "/auth/register",
        json={
            "username": "loginuser",
            "email": "login@example.com",
            "password": "StrongPassword123!",
            "terms_accepted": True
        }
    )
    
    # Login
    response = await test_client.post(
        "/auth/login",
        json={
            "identifier": "login@example.com",
            "password": "StrongPassword123!"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in response.cookies


@pytest.mark.asyncio
async def test_login_wrong_password(test_client):
    await test_client.post(
        "/auth/register",
        json={
            "username": "loginuser2",
            "email": "login2@example.com",
            "password": "StrongPassword123!",
            "terms_accepted": True
        }
    )
    
    response = await test_client.post(
        "/auth/login",
        json={
            "identifier": "login2@example.com",
            "password": "WrongPassword!"
        }
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_user_not_found(test_client):
    response = await test_client.post(
        "/auth/login",
        json={
            "identifier": "notfound@example.com",
            "password": "StrongPassword123!"
        }
    )
    assert response.status_code == 401
