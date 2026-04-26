import pytest
import pytest_asyncio

@pytest_asyncio.fixture
async def auth_client(test_client):
    # Register and login to get access token
    await test_client.post(
        "/auth/register",
        json={
            "username": "user123",
            "email": "user123@example.com",
            "password": "StrongPassword123!",
            "terms_accepted": True
        }
    )
    res = await test_client.post(
        "/auth/login",
        json={
            "identifier": "user123@example.com",
            "password": "StrongPassword123!"
        }
    )
    token = res.json()["access_token"]
    # Return a client with Auth headers set
    class AuthClientWrapper:
        def __init__(self, client, token):
            self.client = client
            self.headers = {"Authorization": f"Bearer {token}"}

        async def get(self, url, **kwargs):
            headers = kwargs.pop("headers", {})
            headers.update(self.headers)
            return await self.client.get(url, headers=headers, **kwargs)

        async def post(self, url, **kwargs):
            headers = kwargs.pop("headers", {})
            headers.update(self.headers)
            return await self.client.post(url, headers=headers, **kwargs)

        async def delete(self, url, **kwargs):
            headers = kwargs.pop("headers", {})
            headers.update(self.headers)
            return await self.client.delete(url, headers=headers, **kwargs)

    return AuthClientWrapper(test_client, token)


@pytest.mark.asyncio
async def test_get_me(auth_client):
    response = await auth_client.get("/users/me")
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "user123@example.com"
    assert data["username"] == "user123"


@pytest.mark.asyncio
async def test_get_me_unauthorized(test_client):
    response = await test_client.get("/users/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_my_identities(auth_client):
    response = await auth_client.get("/users/me/identities")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["provider"] == "password"


@pytest.mark.asyncio
async def test_api_keys_lifecycle(auth_client):
    # 1. Create API Key
    res_create = await auth_client.post("/users/me/api-keys", json={"name": "My Test Key"})
    assert res_create.status_code == 201
    create_data = res_create.json()
    assert create_data["name"] == "My Test Key"
    assert "api_key" in create_data
    assert create_data["api_key"].startswith("ivr_")
    assert create_data["is_active"] is True
    
    key_id = create_data["id"]
    
    # 2. List API Keys
    res_list = await auth_client.get("/users/me/api-keys")
    assert res_list.status_code == 200
    list_data = res_list.json()
    assert len(list_data) == 1
    assert list_data[0]["id"] == key_id
    assert list_data[0]["name"] == "My Test Key"
    assert "api_key" not in list_data[0] # Should not return plaintext key in list
    assert list_data[0]["is_active"] is True
    
    # 3. Deactivate API Key
    res_del = await auth_client.delete(f"/users/me/api-keys/{key_id}")
    assert res_del.status_code == 200
    
    # 4. Verify deactivated
    res_list2 = await auth_client.get("/users/me/api-keys")
    assert res_list2.json()[0]["is_active"] is False
