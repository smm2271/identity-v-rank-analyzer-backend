from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pytest
from fastapi import HTTPException, Request, status
from fastapi.testclient import TestClient

from app import app
from routes.dependencies import get_api_key_service, get_current_user


@dataclass
class FakeUser:
    id: uuid.UUID
    username: Optional[str]
    email: Optional[str]
    created_at: datetime
    token_ver: int


@dataclass
class FakeApiKey:
    id: uuid.UUID
    user_id: uuid.UUID
    key_hash: str
    name: Optional[str]
    is_active: bool
    last_used_at: Optional[datetime]
    created_at: datetime


class FakeApiKeyService:
    def __init__(self) -> None:
        self._items: dict[uuid.UUID, FakeApiKey] = {}

    async def create_api_key(self, *, user_id: uuid.UUID, key_hash: str, name: Optional[str] = None) -> FakeApiKey:
        item = FakeApiKey(
            id=uuid.uuid4(),
            user_id=user_id,
            key_hash=key_hash,
            name=name,
            is_active=True,
            last_used_at=None,
            created_at=datetime.utcnow(),
        )
        self._items[item.id] = item
        return item

    async def get_all_by_user(self, user_id: uuid.UUID, *, active_only: bool = False) -> list[FakeApiKey]:
        result = [v for v in self._items.values() if v.user_id == user_id]
        if active_only:
            result = [v for v in result if v.is_active]
        return result

    async def get_by_id(self, key_id: uuid.UUID) -> Optional[FakeApiKey]:
        return self._items.get(key_id)

    async def deactivate(self, key_id: uuid.UUID) -> Optional[FakeApiKey]:
        item = self._items.get(key_id)
        if item is None:
            return None
        item.is_active = False
        return item


@pytest.fixture()
def client_and_state():
    user = FakeUser(
        id=uuid.uuid4(),
        username="tester",
        email="tester@example.com",
        created_at=datetime.utcnow(),
        token_ver=1,
    )
    fake_api_key_service = FakeApiKeyService()

    async def fake_current_user(request: Request):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="缺少有效的 Authorization header",
            )
        return user

    app.dependency_overrides[get_current_user] = fake_current_user
    app.dependency_overrides[get_api_key_service] = lambda: fake_api_key_service

    with TestClient(app) as client:
        yield client, user, fake_api_key_service

    app.dependency_overrides.clear()


def test_create_api_key_requires_bearer(client_and_state):
    client, _, _ = client_and_state

    resp = client.post(
        "/users/me/api-keys",
        json={"name": "CLI key"},
        headers={"X-API-Key": "fake-old-key"},
    )

    assert resp.status_code == 401


def test_create_api_key_success_with_bearer(client_and_state):
    client, _, _ = client_and_state

    resp = client.post(
        "/users/me/api-keys",
        json={"name": "CLI key"},
        headers={"Authorization": "Bearer test-token"},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "CLI key"
    assert body["is_active"] is True
    assert body["api_key"].startswith("ivr_")


def test_list_api_keys_does_not_expose_plain_key(client_and_state):
    client, _, _ = client_and_state

    create_resp = client.post(
        "/users/me/api-keys",
        json={"name": "List key"},
        headers={"Authorization": "Bearer test-token"},
    )
    assert create_resp.status_code == 201

    list_resp = client.get(
        "/users/me/api-keys",
        headers={"Authorization": "Bearer test-token"},
    )

    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["name"] == "List key"
    assert "api_key" not in items[0]


def test_deactivate_api_key_success(client_and_state):
    client, _, fake_api_key_service = client_and_state

    create_resp = client.post(
        "/users/me/api-keys",
        json={"name": "To revoke"},
        headers={"Authorization": "Bearer test-token"},
    )
    key_id = create_resp.json()["id"]

    delete_resp = client.delete(
        f"/users/me/api-keys/{key_id}",
        headers={"Authorization": "Bearer test-token"},
    )

    assert delete_resp.status_code == 200
    assert delete_resp.json()["message"] == "API Key 已停用"

    key_obj = None

    # 檢查 Fake service 中狀態已變更
    for item in fake_api_key_service._items.values():
        if str(item.id) == key_id:
            key_obj = item
            break

    assert key_obj is not None
    assert key_obj.is_active is False
