import uuid
from datetime import datetime, timezone

import pytest

from database.service import UserService


@pytest.mark.asyncio
async def test_create_user_and_get_by_email(session_factory):
    user_svc = UserService(session_factory)
    
    agreed_time = datetime.now(timezone.utc).replace(tzinfo=None)
    user = await user_svc.create_user(
        username="testuser",
        email="test@example.com",
        agreed_to_terms_at=agreed_time
    )
    
    assert user is not None
    assert user.id is not None
    assert user.username == "testuser"
    assert user.email == "test@example.com"
    assert user.token_ver == 1
    
    fetched_user = await user_svc.get_by_email("test@example.com")
    assert fetched_user is not None
    assert fetched_user.id == user.id


@pytest.mark.asyncio
async def test_create_user_with_identity(session_factory):
    user_svc = UserService(session_factory)
    
    agreed_time = datetime.now(timezone.utc).replace(tzinfo=None)
    user = await user_svc.create_user(
        username="oauthuser",
        email="oauth@example.com",
        agreed_to_terms_at=agreed_time,
        provider="google",
        provider_key="google-123",
        secret_hash="fake-hash"
    )
    
    # Verify the user is created
    assert user is not None
    assert user.username == "oauthuser"
    
    # Fetch user with identities
    user_with_identities = await user_svc.get_with_identities(user.id)
    assert user_with_identities is not None
    assert len(user_with_identities.identities) == 1
    
    identity = user_with_identities.identities[0]
    assert identity.provider == "google"
    assert identity.provider_key == "google-123"
    assert identity.secret_hash == "fake-hash"


@pytest.mark.asyncio
async def test_increment_token_ver(session_factory):
    user_svc = UserService(session_factory)
    
    agreed_time = datetime.now(timezone.utc).replace(tzinfo=None)
    user = await user_svc.create_user(
        username="revoker",
        email="revoke@example.com",
        agreed_to_terms_at=agreed_time
    )
    
    assert user.token_ver == 1
    
    updated_user = await user_svc.increment_token_ver(user.id)
    assert updated_user is not None
    assert updated_user.token_ver == 2
    
    # Verify in DB
    fetched = await user_svc.get_by_id(user.id)
    assert fetched.token_ver == 2


@pytest.mark.asyncio
async def test_get_by_identifier(session_factory):
    user_svc = UserService(session_factory)
    
    agreed_time = datetime.now(timezone.utc).replace(tzinfo=None)
    user = await user_svc.create_user(
        username="identuser",
        email="ident@example.com",
        agreed_to_terms_at=agreed_time
    )
    
    # Find by username
    found1 = await user_svc.get_by_identifier("identuser")
    assert found1 is not None
    assert found1.id == user.id
    
    # Find by email
    found2 = await user_svc.get_by_identifier("ident@example.com")
    assert found2 is not None
    assert found2.id == user.id
    
    # Not found
    found3 = await user_svc.get_by_identifier("notexist")
    assert found3 is None
