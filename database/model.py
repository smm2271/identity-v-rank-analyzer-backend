import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    String,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Index,
    UniqueConstraint,
    func
)
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[Optional[str]] = mapped_column(String(50), unique=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    token_ver: Mapped[int] = mapped_column(Integer, nullable=False)
    agreed_to_terms_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Relationships
    identities: Mapped[List["UserIdentity"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    api_keys: Mapped[List["ApiKey"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    matches: Mapped[List["GameMatch"]] = relationship(back_populates="creator")
    login_logs: Mapped[List["UserLoginLog"]] = relationship(back_populates="user")


class UserIdentity(Base):
    __tablename__ = "user_identities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    provider: Mapped[str] = mapped_column(String(20))
    provider_key: Mapped[str] = mapped_column(String(255))
    secret_hash: Mapped[Optional[str]] = mapped_column(String(255))

    user: Mapped["User"] = relationship(back_populates="identities")

    __table_args__ = (
        UniqueConstraint("provider", "provider_key", name="uq_provider_key"),
    )


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    key_hash: Mapped[str] = mapped_column(String(64))
    name: Mapped[Optional[str]] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="api_keys")


class GameMatch(Base):
    __tablename__ = "game_matches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_guuid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    creator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    scene_id: Mapped[Optional[int]] = mapped_column(Integer)
    match_type: Mapped[Optional[int]] = mapped_column(Integer)
    rank_level: Mapped[Optional[int]] = mapped_column(Integer)
    kill_num: Mapped[Optional[int]] = mapped_column(Integer)
    utype: Mapped[Optional[int]] = mapped_column(Integer)
    pid: Mapped[Optional[int]] = mapped_column(Integer)
    game_save_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    cipher_progress: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    creator: Mapped["User"] = relationship(back_populates="matches")
    player_infos: Mapped[List["PlayerInfo"]] = relationship(back_populates="match", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("room_guuid", "creator_id", name="uq_game_matches_room_creator"),
    )


class PlayerInfo(Base):
    __tablename__ = "player_info"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("game_matches.id"))
    player_id: Mapped[int] = mapped_column(Integer, nullable=False)
    player_name: Mapped[Optional[str]] = mapped_column(String(14))
    character_id: Mapped[int] = mapped_column(Integer, nullable=False)
    res_type: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    match: Mapped["GameMatch"] = relationship(back_populates="player_infos")

    __table_args__ = (
        Index("ix_player_info_match_id", "match_id"),
        Index("ix_player_info_created_at", "created_at"),
    )


class UserLoginLog(Base):
    __tablename__ = "user_login_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id"), nullable=True)
    identifier: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[Optional[str]] = mapped_column(String(20))
    failure_reason: Mapped[Optional[str]] = mapped_column(String(50))
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="login_logs")

    __table_args__ = (
        Index("ix_login_logs_user_id", "user_id"),
        Index("ix_login_logs_ip_address", "ip_address"),
    )