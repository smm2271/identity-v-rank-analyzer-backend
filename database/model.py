import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import String, Integer, DateTime, Boolean, ForeignKey, JSON, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# 定義基礎類別
class Base(DeclarativeBase):
    pass


# 1. 使用者主表
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(50))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now())
    # JWT撤銷機制版本號，當用戶登出或密碼變更時，增加此版本號以使舊 token 失效
    token_ver: Mapped[int] = mapped_column(Integer, default=1)
    agreed_to_terms_at: Mapped[datetime] = mapped_column(DateTime)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 關聯
    identities: Mapped[List["UserIdentity"]] = relationship(
        back_populates="user", cascade="all, delete-orphan")
    api_keys: Mapped[List["APIKey"]] = relationship(back_populates="user")
    matches: Mapped[List["GameMatch"]] = relationship(back_populates="creator")


# 2. 身分驗證 (支援 Google/Discord OAuth2)
class UserIdentity(Base):
    __tablename__ = "user_identities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    provider: Mapped[str] = mapped_column(
        String(20))  # 'password', 'google', 'discord'
    provider_key: Mapped[str] = mapped_column(String(255))
    secret_hash: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True)

    user: Mapped["User"] = relationship(back_populates="identities")


# 3. 客戶端用 API Key 表 (供 Python CLI 使用 )
class APIKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    key_hash: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="api_keys")


# 4. 遊戲對戰全局資訊表 (核心數據分析用 )
class GameMatch(Base):
    __tablename__ = "game_matches"

    room_guuid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True)
    creater_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    scene_id: Mapped[int] = mapped_column(Integer)  # 地圖 ID
    match_type: Mapped[int] = mapped_column(Integer)  # 1:排位, 2:匹配, 3:五排
    rank_level: Mapped[int] = mapped_column(Integer)
    kill_num: Mapped[int] = mapped_column(Integer)
    utype: Mapped[int] = mapped_column(Integer)  # 1:監管 2:求生
    pid: Mapped[int] = mapped_column(Integer)  # 角色 ID
    game_save_time: Mapped[datetime] = mapped_column(DateTime)
    # 存儲密碼機進度
    cipher_progress: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now())

    creator: Mapped["User"] = relationship(back_populates="matches")
    players: Mapped[List["PlayerInfo"]] = relationship(back_populates="match")


# 5. 對局玩家資料
class PlayerInfo(Base):
    __tablename__ = "player_info"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True)
    player_name: Mapped[str] = mapped_column(String(14))
    character_id: Mapped[int] = mapped_column(Integer)
    res_type: Mapped[int] = mapped_column(Integer)
    game_uuid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("game_matches.room_guuid"))

    match: Mapped["GameMatch"] = relationship(back_populates="players")


# 6. 登入日誌表
class UserLoginLog(Base):
    __tablename__ = "user_login_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id"), nullable=True)
    identifier: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20))  # success, failed, locked
    failure_reason: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True)
    ip_address: Mapped[str] = mapped_column(String(45))
    user_agent: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now())
