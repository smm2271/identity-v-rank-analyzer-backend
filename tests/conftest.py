import asyncio
import os
import subprocess
import time
from typing import AsyncGenerator

import pytest
import pytest_asyncio
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
async def session_factory(db_engine) -> async_sessionmaker[AsyncSession]:
    """Provide an async_sessionmaker bound to the test engine."""
    return async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False
    )
