import uuid
from datetime import datetime

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def auth_client(test_client):
    # Register and login to get access token
    await test_client.post(
        "/auth/register",
        json={
            "username": "matchuser",
            "email": "match@example.com",
            "password": "StrongPassword123!",
            "terms_accepted": True
        }
    )
    res = await test_client.post(
        "/auth/login",
        json={
            "identifier": "match@example.com",
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

    return AuthClientWrapper(test_client, token)


@pytest.mark.asyncio
async def test_upload_match(auth_client):
    room_guuid = str(uuid.uuid4())
    payload = {
        "room_guuid": room_guuid,
        "scene_id": 1,
        "match_type": 2,
        "rank_level": 5,
        "kill_num": 4,
        "utype": 1,
        "pid": 1001,
        "game_save_time": datetime.utcnow().isoformat() + "Z",
        "cipher_progress": {"1": 100},
        "players": [
            {"player_id": 1, "character_id": 1001, "player_name": "P1"},
            {"player_id": 2, "character_id": 2001, "player_name": "P2"}
        ],
        "ladder_score_info": [
            {"pid": 1001, "score": 5000}
        ]
    }
    
    response = await auth_client.post("/api/v1/matches", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None


@pytest.mark.asyncio
async def test_upload_match_duplicate(auth_client):
    room_guuid = str(uuid.uuid4())
    payload = {
        "room_guuid": room_guuid,
        "scene_id": 1,
        "match_type": 2,
        "game_save_time": datetime.utcnow().isoformat() + "Z",
        "ladder_score_info": [
            {"pid": 1001, "score": 5000}
        ]
    }
    
    # First upload
    res1 = await auth_client.post("/api/v1/matches", json=payload)
    assert res1.status_code == 201
    
    # Second upload with same room_guuid
    res2 = await auth_client.post("/api/v1/matches", json=payload)
    assert res2.status_code == 409
    assert "此對戰紀錄已上傳過" in res2.json()["detail"]


@pytest.mark.asyncio
async def test_get_matches(auth_client):
    # Upload 2 matches
    for _ in range(2):
        payload = {
            "room_guuid": str(uuid.uuid4()),
            "scene_id": 1,
            "match_type": 2,
            "game_save_time": datetime.utcnow().isoformat() + "Z",
            "ladder_score_info": [
                {"pid": 1001, "score": 5000}
            ]
        }
        await auth_client.post("/api/v1/matches", json=payload)
        
    response = await auth_client.get("/api/v1/matches?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] == 2
    assert len(data["items"]) == 2
