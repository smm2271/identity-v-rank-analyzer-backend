import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from database.service import RefreshTokenService, UserService


@pytest_asyncio.fixture
async def test_user(session_factory):
    user_svc = UserService(session_factory)
    return await user_svc.create_user(
        username="refreshuser",
        email="refresh@example.com",
        agreed_to_terms_at=datetime.now(timezone.utc).replace(tzinfo=None)
    )


@pytest.mark.asyncio
async def test_create_and_get_refresh_token(session_factory, test_user):
    token_svc = RefreshTokenService(session_factory)
    
    jti = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7)
    
    token = await token_svc.create_refresh_token(
        user_id=test_user.id,
        jti=jti,
        expires_at=expires_at
    )
    
    assert token is not None
    assert token.jti == jti
    assert token.is_active is True
    
    fetched = await token_svc.get_active_by_jti(jti)
    assert fetched is not None
    assert fetched.id == token.id


@pytest.mark.asyncio
async def test_revoke_refresh_token(session_factory, test_user):
    token_svc = RefreshTokenService(session_factory)
    
    jti = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7)
    
    await token_svc.create_refresh_token(
        user_id=test_user.id,
        jti=jti,
        expires_at=expires_at
    )
    
    # Revoke it
    success = await token_svc.revoke_by_jti(jti)
    assert success is True
    
    # Try fetching it active
    fetched = await token_svc.get_active_by_jti(jti)
    assert fetched is None
    
    # Revoke again should return False
    success_again = await token_svc.revoke_by_jti(jti)
    assert success_again is False
