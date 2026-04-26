from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from auth.jwt_auth.jwt_service import (
    JWTService,
    TokenExpiredError,
    TokenInvalidError,
    TokenRevokedError,
)


class MockKeyManager:
    def __init__(self):
        # Generate an in-memory RSA key pair for testing
        private_key_obj = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        self.private_key = private_key_obj.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_key_obj = private_key_obj.public_key()
        self.public_key = public_key_obj.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )


class MockUserService:
    def __init__(self, user_dict=None):
        self.users = user_dict or {}

    async def get_by_id(self, user_id: uuid.UUID):
        return self.users.get(user_id)


class MockUser:
    def __init__(self, id: uuid.UUID, token_ver: int):
        self.id = id
        self.token_ver = token_ver


@pytest.fixture
def key_manager():
    return MockKeyManager()


@pytest.fixture
def jwt_service(key_manager):
    return JWTService(key_manager=key_manager)


def test_create_access_token(jwt_service):
    user_uuid = uuid.uuid4()
    token = jwt_service.create_access_token(
        user_uuid=user_uuid,
        user_name="tester",
        token_ver=1,
    )
    
    # Verify the created token
    payload = jwt_service.verify_token(token)
    assert payload.uuid == user_uuid
    assert payload.token_ver == 1
    assert payload.token_type == "access"
    assert payload.jti is None


def test_create_refresh_token(jwt_service):
    user_uuid = uuid.uuid4()
    token, jti = jwt_service.create_refresh_token(
        user_uuid=user_uuid,
        token_ver=1,
    )
    
    payload = jwt_service.verify_token(token)
    assert payload.uuid == user_uuid
    assert payload.token_ver == 1
    assert payload.token_type == "refresh"
    assert payload.jti == jti


def test_verify_token_expired(jwt_service, key_manager):
    user_uuid = uuid.uuid4()
    now = datetime.now(timezone.utc)
    sub_data = json.dumps({"uuid": str(user_uuid), "token_ver": 1, "user_name": "test"})
    # Create an explicitly expired token
    payload = {
        "sub": sub_data,
        "type": "access",
        "iat": now - timedelta(hours=2),
        "exp": now - timedelta(hours=1),
    }
    
    expired_token = jwt.encode(payload, key_manager.private_key, algorithm="RS256")
    
    with pytest.raises(TokenExpiredError):
        jwt_service.verify_token(expired_token)


def test_verify_token_invalid_signature(jwt_service, key_manager):
    user_uuid = uuid.uuid4()
    token = jwt_service.create_access_token(
        user_uuid=user_uuid,
        user_name="tester",
        token_ver=1,
    )
    
    # Tamper with the token
    invalid_token = token[:-5] + "aaaaa"
    
    with pytest.raises(TokenInvalidError):
        jwt_service.verify_token(invalid_token)


@pytest.mark.asyncio
async def test_verify_and_check_revocation_success(jwt_service):
    user_uuid = uuid.uuid4()
    token = jwt_service.create_access_token(
        user_uuid=user_uuid,
        user_name="tester",
        token_ver=1,
    )
    
    user = MockUser(id=user_uuid, token_ver=1)
    user_svc = MockUserService({user_uuid: user})
    
    payload = await jwt_service.verify_and_check_revocation(token, user_svc)
    assert payload.uuid == user_uuid


@pytest.mark.asyncio
async def test_verify_and_check_revocation_user_not_found(jwt_service):
    user_uuid = uuid.uuid4()
    token = jwt_service.create_access_token(
        user_uuid=user_uuid,
        user_name="tester",
        token_ver=1,
    )
    
    # Empty user service
    user_svc = MockUserService()
    
    with pytest.raises(TokenInvalidError, match="使用者不存在"):
        await jwt_service.verify_and_check_revocation(token, user_svc)


@pytest.mark.asyncio
async def test_verify_and_check_revocation_token_revoked(jwt_service):
    user_uuid = uuid.uuid4()
    # Token issued with token_ver = 1
    token = jwt_service.create_access_token(
        user_uuid=user_uuid,
        user_name="tester",
        token_ver=1,
    )
    
    # User's current token_ver is 2 (revoked)
    user = MockUser(id=user_uuid, token_ver=2)
    user_svc = MockUserService({user_uuid: user})
    
    with pytest.raises(TokenRevokedError):
        await jwt_service.verify_and_check_revocation(token, user_svc)
