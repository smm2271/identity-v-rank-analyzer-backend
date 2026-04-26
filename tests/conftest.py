import asyncio
import os
import subprocess
import time
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database.model import Base

# Test database configuration
DB_USER = "test_user"
DB_PASSWORD = "test_pass"
DB_NAME = "test_db"
DB_PORT = 54320
CONTAINER_NAME = "idv_analyzer_test_db"
TEST_DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@localhost:{DB_PORT}/{DB_NAME}"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Start a PostgreSQL Docker container for the test session."""
    # Ensure no old container is lingering
    subprocess.run(["docker", "rm", "-f", CONTAINER_NAME], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Start the container
    subprocess.run([
        "docker", "run", "-d",
        "--name", CONTAINER_NAME,
        "-e", f"POSTGRES_USER={DB_USER}",
        "-e", f"POSTGRES_PASSWORD={DB_PASSWORD}",
        "-e", f"POSTGRES_DB={DB_NAME}",
        "-p", f"{DB_PORT}:5432",
        "postgres:15-alpine"
    ], check=True, stdout=subprocess.DEVNULL)
    
    # Wait for the database to be ready
    print("\nWaiting for test database to start...")
    time.sleep(3) # Initial wait
    
    engine = create_async_engine(TEST_DATABASE_URL)
    
    async def wait_for_db():
        for i in range(30):
            try:
                async with engine.begin() as conn:
                    await conn.execute(text("SELECT 1"))
                return True
            except Exception:
                await asyncio.sleep(1)
        return False
    
    from sqlalchemy import text
    if not asyncio.run(wait_for_db()):
        subprocess.run(["docker", "rm", "-f", CONTAINER_NAME])
        pytest.fail("Could not connect to test database within 30 seconds.")
        
    print("Test database is ready!")
    
    yield
    
    # Teardown the container
    print("\nRemoving test database container...")
    subprocess.run(["docker", "rm", "-f", CONTAINER_NAME], stdout=subprocess.DEVNULL)


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """Create an async engine and tables for each test, then drop them."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_client(session_factory):
    from app import app
    from auth.jwt_auth.jwt_service import JWTService
    from auth.jwt_auth.key_manager import KeyManager
    from auth.login_interface import DiscordOAuthProvider, GoogleOAuthProvider, LoginProviderFactory, PasswordLoginProvider
    from database.service import (
        ApiKeyService,
        CharacterLadderScoreService,
        GameMatchService,
        RefreshTokenService,
        UserIdentityService,
        UserLoginLogService,
        UserService,
    )
    from routes.dependencies import (
        get_api_key_service,
        get_identity_service,
        get_jwt_service,
        get_ladder_score_service,
        get_login_factory,
        get_login_log_service,
        get_match_service,
        get_refresh_token_service,
        get_user_service,
    )

    user_svc = UserService(session_factory)
    identity_svc = UserIdentityService(session_factory)
    login_log_svc = UserLoginLogService(session_factory)
    api_key_svc = ApiKeyService(session_factory)
    match_svc = GameMatchService(session_factory)
    ladder_score_svc = CharacterLadderScoreService(session_factory)
    refresh_token_svc = RefreshTokenService(session_factory)

    key_manager = KeyManager()
    jwt_svc = JWTService(key_manager)

    login_factory = LoginProviderFactory()
    login_factory.register(GoogleOAuthProvider())
    login_factory.register(DiscordOAuthProvider())
    login_factory.register(PasswordLoginProvider(identity_lookup=identity_svc))

    app.dependency_overrides[get_user_service] = lambda: user_svc
    app.dependency_overrides[get_identity_service] = lambda: identity_svc
    app.dependency_overrides[get_login_log_service] = lambda: login_log_svc
    app.dependency_overrides[get_api_key_service] = lambda: api_key_svc
    app.dependency_overrides[get_match_service] = lambda: match_svc
    app.dependency_overrides[get_ladder_score_service] = lambda: ladder_score_svc
    app.dependency_overrides[get_refresh_token_service] = lambda: refresh_token_svc
    app.dependency_overrides[get_jwt_service] = lambda: jwt_svc
    app.dependency_overrides[get_login_factory] = lambda: login_factory

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def session_factory(db_engine) -> async_sessionmaker[AsyncSession]:
    """Provide an async_sessionmaker bound to the test engine."""
    return async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False
    )
