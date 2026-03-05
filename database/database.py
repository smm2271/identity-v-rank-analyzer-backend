import os
from typing import AsyncGenerator
import dotenv
from database.model import Base  # 引入模型定義，確保 metadata 可用來建立表格
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

# 1. 資料庫連線字串
dotenv.load_dotenv()  # 從 .env 檔案載入環境變數
DATABASE_URL = os.getenv("DATABASE_URL", f"postgresql+asyncpg://{os.getenv('db_user')}:{os.getenv('db_password')}@{os.getenv('db_host')}:{os.getenv('db_port')}/{os.getenv('db_name')}")

# 2. 建立非同步引擎 (Engine)
engine = create_async_engine(
    DATABASE_URL,
    echo=True, 
    future=True,
    pool_size=10,         # 連線池大小
    max_overflow=20       # 超出連線池時最多可擴展的連線數
)

# 3. 建立 Session 工廠
# expire_on_commit=False 是為了在 commit 後依然能存取物件屬性，避免非同步錯誤
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# 4. Dependency (FastAPI 依賴注入用)
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def create_tables():
    async with engine.begin() as conn:
        print("正在建立資料庫表...")
        await conn.run_sync(Base.metadata.create_all)
        print("所有資料表已成功建立！")
            
if __name__ == "__main__":
    # 建構資料庫表格 (如果尚未存在)
    import asyncio
    asyncio.run(create_tables())