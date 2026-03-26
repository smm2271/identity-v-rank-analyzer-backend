"""
Database Service Layer
======================
遵循 SOLID 原則設計的非同步資料庫服務層。

- S: 每個 Model 對應獨立的 Service 類別，各自負責單一職責。
- O: 透過泛型 BaseRepository 提供通用 CRUD，子類別擴展而非修改。
- L: 所有 Repository 可替換使用，行為一致。
- I: 透過 Protocol 定義最小介面，消費端只依賴所需方法。
- D: Service 依賴 async_sessionmaker 抽象，由外部注入；
      每次操作獨立建立 session，避免 session 共用問題。
"""

import uuid
from datetime import datetime
from typing import (
    Any,
    Dict,
    Generic,
    List,
    Optional,
    Protocol,
    Sequence,
    Type,
    TypeVar,
    runtime_checkable,
)

from sqlalchemy import select, update, delete, func, or_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from database.model import (
    Base,
    User,
    UserIdentity,
    ApiKey,
    GameMatch,
    PlayerInfo,
    UserLoginLog,
    CharacterLadderScore,
)

# ──────────────────────────────────────────────
# Type Variables
# ──────────────────────────────────────────────
ModelT = TypeVar("ModelT", bound=Base)


# ──────────────────────────────────────────────
# Protocols (Interface Segregation)
# ──────────────────────────────────────────────
@runtime_checkable
class ReadableRepository(Protocol[ModelT]):
    """唯讀操作介面"""

    async def get_by_id(self, id: uuid.UUID) -> Optional[ModelT]: ...
    async def get_all(self, *, offset: int = 0,
                      limit: int = 100) -> Sequence[ModelT]: ...

    async def count(self) -> int: ...


@runtime_checkable
class WritableRepository(Protocol[ModelT]):
    """寫入操作介面"""

    async def create(self, **kwargs: Any) -> ModelT: ...
    async def update_by_id(self, id: uuid.UUID, **
                           kwargs: Any) -> Optional[ModelT]: ...

    async def delete_by_id(self, id: uuid.UUID) -> bool: ...


# ──────────────────────────────────────────────
# Generic Base Repository (Open/Closed Principle)
# ──────────────────────────────────────────────
class BaseRepository(Generic[ModelT]):
    """
    泛型基底 Repository，提供通用的 CRUD 操作。

    注入 async_sessionmaker 而非 AsyncSession：
    - 每次操作獨立建立 session，不會跨操作共用。
    - Service 可安全作為長生命週期物件（如 singleton）。
    - 子類別應擴展此類別以新增特定業務邏輯，而非修改現有方法。
    """

    def __init__(self, model: Type[ModelT], session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._model = model
        self._session_factory = session_factory

    async def get_by_id(self, id: uuid.UUID) -> Optional[ModelT]:
        """根據主鍵 ID 查詢單一記錄"""
        async with self._session_factory() as session:
            return await session.get(self._model, id)

    async def get_all(self, *, offset: int = 0, limit: int = 100) -> Sequence[ModelT]:
        """取得分頁記錄列表"""
        async with self._session_factory() as session:
            stmt = select(self._model).offset(offset).limit(limit)
            result = await session.execute(stmt)
            return result.scalars().all()

    async def count(self) -> int:
        """取得總記錄數"""
        async with self._session_factory() as session:
            stmt = select(func.count()).select_from(self._model)
            result = await session.execute(stmt)
            return result.scalar_one()

    async def create(self, **kwargs: Any) -> ModelT:
        """建立新記錄"""
        async with self._session_factory() as session:
            instance = self._model(**kwargs)
            session.add(instance)
            await session.commit()
            return instance

    async def update_by_id(self, id: uuid.UUID, **kwargs: Any) -> Optional[ModelT]:
        """根據 ID 更新記錄，返回更新後的實體"""
        async with self._session_factory() as session:
            stmt = (
                update(self._model)
                .where(self._model.id == id)  # type: ignore[attr-defined]
                .values(**kwargs)
                .returning(self._model)
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.scalar_one_or_none()

    async def delete_by_id(self, id: uuid.UUID) -> bool:
        """根據 ID 刪除記錄，返回是否成功"""
        async with self._session_factory() as session:
            stmt = (
                delete(self._model)
                .where(self._model.id == id)  # type: ignore[attr-defined]
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0  # type: ignore[union-attr]


# ──────────────────────────────────────────────
# User Service (Single Responsibility)
# ──────────────────────────────────────────────
class UserService(BaseRepository[User]):
    """使用者相關的資料庫操作"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(User, session_factory)

    async def create_user(
        self,
        *,
        username: Optional[str] = None,
        email: Optional[str] = None,
        token_ver: int = 1,
        agreed_to_terms_at: datetime,
        provider: Optional[str] = None,
        provider_key: Optional[str] = None,
        secret_hash: Optional[str] = None,
    ) -> User:
        """
        建立新使用者，可同時建立第一筆身份驗證來源。

        User + UserIdentity 在同一個 transaction 中建立，
        確保不會出現有 User 卻沒有 Identity 的狀況。
        """
        async with self._session_factory() as session:
            user = User(
                username=username,
                email=email,
                token_ver=token_ver,
                agreed_to_terms_at=agreed_to_terms_at,
            )
            session.add(user)

            # 若提供了 provider 資訊，一併建立身份
            if provider and provider_key:
                identity = UserIdentity(
                    user=user,
                    provider=provider,
                    provider_key=provider_key,
                    secret_hash=secret_hash,
                )
                session.add(identity)

            await session.commit()
            return user

    async def get_by_username(self, username: str) -> Optional[User]:
        """根據使用者名稱查詢"""
        async with self._session_factory() as session:
            stmt = select(User).where(User.username == username)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        """根據 Email 查詢"""
        async with self._session_factory() as session:
            stmt = select(User).where(User.email == email)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_by_identifier(self, identifier: str) -> Optional[User]:
        """以 Email 或 Username 查詢使用者"""
        async with self._session_factory() as session:
            stmt = select(User).where(
                or_(
                    User.email == identifier,
                    User.username == identifier,
                )
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_with_identities(self, user_id: uuid.UUID) -> Optional[User]:
        """取得使用者及其所有身份驗證方式"""
        async with self._session_factory() as session:
            stmt = (
                select(User)
                .options(selectinload(User.identities))
                .where(User.id == user_id)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def increment_token_ver(self, user_id: uuid.UUID) -> Optional[User]:
        """遞增 token 版本號（用於使所有 token 失效）"""
        async with self._session_factory() as session:
            stmt = (
                update(User)
                .where(User.id == user_id)
                .values(token_ver=User.token_ver + 1)
                .returning(User)
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.scalar_one_or_none()


# ──────────────────────────────────────────────
# UserIdentity Service
# ──────────────────────────────────────────────
class UserIdentityService(BaseRepository[UserIdentity]):
    """使用者身份驗證來源的資料庫操作"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(UserIdentity, session_factory)

    async def create_identity(
        self,
        *,
        user_id: uuid.UUID,
        provider: str,
        provider_key: str,
        secret_hash: Optional[str] = None,
    ) -> UserIdentity:
        """為既有使用者新增一筆身份驗證來源"""
        async with self._session_factory() as session:
            identity = UserIdentity(
                user_id=user_id,
                provider=provider,
                provider_key=provider_key,
                secret_hash=secret_hash,
            )
            session.add(identity)
            await session.commit()
            return identity

    async def get_by_provider(
        self, provider: str, provider_key: str
    ) -> Optional[UserIdentity]:
        """根據第三方供應商與 key 查詢身份"""
        async with self._session_factory() as session:
            stmt = select(UserIdentity).where(
                UserIdentity.provider == provider,
                UserIdentity.provider_key == provider_key,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_all_by_user(self, user_id: uuid.UUID) -> Sequence[UserIdentity]:
        """取得某使用者的所有身份驗證來源"""
        async with self._session_factory() as session:
            stmt = select(UserIdentity).where(UserIdentity.user_id == user_id)
            result = await session.execute(stmt)
            return result.scalars().all()


# ──────────────────────────────────────────────
# ApiKey Service
# ──────────────────────────────────────────────
class ApiKeyService(BaseRepository[ApiKey]):
    """API Key 的資料庫操作"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(ApiKey, session_factory)

    async def create_api_key(
        self,
        *,
        user_id: uuid.UUID,
        key_hash: str,
        name: Optional[str] = None,
    ) -> ApiKey:
        """為使用者建立新的 API Key"""
        async with self._session_factory() as session:
            api_key = ApiKey(
                user_id=user_id,
                key_hash=key_hash,
                name=name,
                is_active=True,
            )
            session.add(api_key)
            await session.commit()
            return api_key

    async def get_by_key_hash(self, key_hash: str) -> Optional[ApiKey]:
        """根據 key hash 查詢（用於驗證 API Key）"""
        async with self._session_factory() as session:
            stmt = select(ApiKey).where(
                ApiKey.key_hash == key_hash,
                ApiKey.is_active.is_(True),
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_all_by_user(
        self, user_id: uuid.UUID, *, active_only: bool = False
    ) -> Sequence[ApiKey]:
        """取得某使用者的所有 API Keys"""
        async with self._session_factory() as session:
            stmt = select(ApiKey).where(ApiKey.user_id == user_id)
            if active_only:
                stmt = stmt.where(ApiKey.is_active.is_(True))
            result = await session.execute(stmt)
            return result.scalars().all()

    async def deactivate(self, key_id: uuid.UUID) -> Optional[ApiKey]:
        """停用某個 API Key"""
        return await self.update_by_id(key_id, is_active=False)

    async def touch_last_used(self, key_id: uuid.UUID) -> None:
        """更新 API Key 最後使用時間"""
        async with self._session_factory() as session:
            stmt = (
                update(ApiKey)
                .where(ApiKey.id == key_id)
                .values(last_used_at=func.now())
            )
            await session.execute(stmt)
            await session.commit()


# ──────────────────────────────────────────────
# GameMatch Service
# ──────────────────────────────────────────────
class GameMatchService(BaseRepository[GameMatch]):
    """遊戲對戰紀錄的資料庫操作"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(GameMatch, session_factory)

    async def create_match(
        self,
        *,
        room_guuid: uuid.UUID,
        uploader_id: uuid.UUID,
        scene_id: Optional[int] = None,
        match_type: Optional[int] = None,
        rank_level: Optional[int] = None,
        kill_num: Optional[int] = None,
        utype: Optional[int] = None,
        pid: Optional[int] = None,
        game_save_time: Optional[datetime] = None,
        cipher_progress: Optional[Dict[str, Any]] = None,
        players: Optional[List[Dict[str, Any]]] = None,
    ) -> GameMatch:
        """
        建立對戰紀錄，可同時建立所有玩家資訊。

        GameMatch + PlayerInfo 在同一個 transaction 中建立，
        確保資料一致性（不會出現有對戰但沒有任何玩家的狀況）。
        """
        async with self._session_factory() as session:
            # Ensure naive UTC if timezone is present to match naive DB column
            if game_save_time and game_save_time.tzinfo:
                game_save_time = game_save_time.replace(tzinfo=None)

            match = GameMatch(
                room_guuid=room_guuid,
                uploader_id=uploader_id,
                scene_id=scene_id,
                match_type=match_type,
                rank_level=rank_level,
                kill_num=kill_num,
                utype=utype,
                pid=pid,
                game_save_time=game_save_time,
                cipher_progress=cipher_progress,
            )
            session.add(match)

            # 若提供了玩家資訊，一併建立
            if players:
                for player_data in players:
                    player = PlayerInfo(match=match, **player_data)
                    session.add(player)

            await session.commit()
            return match

    async def get_by_room_guuid(
        self, room_guuid: uuid.UUID, uploader_id: uuid.UUID
    ) -> Optional[GameMatch]:
        """根據房間 UUID 與上傳者查詢對戰"""
        async with self._session_factory() as session:
            stmt = select(GameMatch).where(
                GameMatch.room_guuid == room_guuid,
                GameMatch.uploader_id == uploader_id,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_with_players(self, match_id: uuid.UUID) -> Optional[GameMatch]:
        """取得對戰紀錄及其所有玩家資訊"""
        async with self._session_factory() as session:
            stmt = (
                select(GameMatch)
                .options(selectinload(GameMatch.player_infos))
                .where(GameMatch.id == match_id)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_matches_by_uploader(
        self,
        uploader_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[GameMatch]:
        """取得某使用者上傳的所有對戰紀錄（分頁）"""
        async with self._session_factory() as session:
            stmt = (
                select(GameMatch)
                .where(GameMatch.uploader_id == uploader_id)
                .order_by(GameMatch.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    async def count_by_uploader(self, uploader_id: uuid.UUID) -> int:
        """取得某使用者的對戰總數"""
        async with self._session_factory() as session:
            stmt = (
                select(func.count())
                .select_from(GameMatch)
                .where(GameMatch.uploader_id == uploader_id)
            )
            result = await session.execute(stmt)
            return result.scalar_one()


# ──────────────────────────────────────────────
# PlayerInfo Service
# ──────────────────────────────────────────────
class PlayerInfoService(BaseRepository[PlayerInfo]):
    """玩家資訊的資料庫操作"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(PlayerInfo, session_factory)

    async def create_player(
        self,
        *,
        match_id: uuid.UUID,
        player_id: int,
        character_id: int,
        player_name: Optional[str] = None,
        res_type: Optional[int] = None,
    ) -> PlayerInfo:
        """建立單筆玩家資訊"""
        async with self._session_factory() as session:
            player = PlayerInfo(
                match_id=match_id,
                player_id=player_id,
                character_id=character_id,
                player_name=player_name,
                res_type=res_type,
            )
            session.add(player)
            await session.commit()
            return player

    async def get_by_match(self, match_id: uuid.UUID) -> Sequence[PlayerInfo]:
        """取得某場對戰的所有玩家資訊"""
        async with self._session_factory() as session:
            stmt = (
                select(PlayerInfo)
                .where(PlayerInfo.match_id == match_id)
                .order_by(PlayerInfo.player_id)
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    async def get_by_character(
        self,
        character_id: int,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> Sequence[PlayerInfo]:
        """根據角色 ID 查詢所有使用該角色的紀錄"""
        async with self._session_factory() as session:
            stmt = (
                select(PlayerInfo)
                .where(PlayerInfo.character_id == character_id)
                .order_by(PlayerInfo.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    async def bulk_create(self, players: List[Dict[str, Any]]) -> Sequence[PlayerInfo]:
        """批次建立多筆玩家資訊"""
        async with self._session_factory() as session:
            instances = [PlayerInfo(**data) for data in players]
            session.add_all(instances)
            await session.commit()
            return instances


# ──────────────────────────────────────────────
# UserLoginLog Service
# ──────────────────────────────────────────────
class UserLoginLogService(BaseRepository[UserLoginLog]):
    """使用者登入紀錄的資料庫操作"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(UserLoginLog, session_factory)

    async def get_by_user(
        self,
        user_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[UserLoginLog]:
        """取得某使用者的登入紀錄（分頁，最新優先）"""
        async with self._session_factory() as session:
            stmt = (
                select(UserLoginLog)
                .where(UserLoginLog.user_id == user_id)
                .order_by(UserLoginLog.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    async def get_by_ip(
        self,
        ip_address: str,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[UserLoginLog]:
        """根據 IP 位址查詢登入紀錄"""
        async with self._session_factory() as session:
            stmt = (
                select(UserLoginLog)
                .where(UserLoginLog.ip_address == ip_address)
                .order_by(UserLoginLog.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    async def get_recent_failures(
        self,
        identifier: str,
        *,
        since: Optional[datetime] = None,
    ) -> Sequence[UserLoginLog]:
        """查詢某帳號最近的登入失敗紀錄（可用於暴力破解偵測）"""
        async with self._session_factory() as session:
            stmt = select(UserLoginLog).where(
                UserLoginLog.identifier == identifier,
                UserLoginLog.status == "failed",
            )
            if since is not None:
                stmt = stmt.where(UserLoginLog.created_at >= since)
            stmt = stmt.order_by(UserLoginLog.created_at.desc())
            result = await session.execute(stmt)
            return result.scalars().all()

    async def log_login(
        self,
        *,
        user_id: Optional[uuid.UUID] = None,
        identifier: Optional[str] = None,
        status: str,
        failure_reason: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> UserLoginLog:
        """記錄一筆登入事件"""
        return await self.create(
            user_id=user_id,
            identifier=identifier,
            status=status,
            failure_reason=failure_reason,
            ip_address=ip_address,
            user_agent=user_agent,
        )


# ──────────────────────────────────────────────
# CharacterLadderScore Service
# ──────────────────────────────────────────────
class CharacterLadderScoreService(BaseRepository[CharacterLadderScore]):
    """認知分紀錄的資料庫操作"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        super().__init__(CharacterLadderScore, session_factory)

    async def create_ladder_score(
        self,
        *,
        user_id: uuid.UUID,
        pid: int,
        score: int,
    ) -> CharacterLadderScore:
        """建立認知分紀錄"""
        return await self.create(
            user_id=user_id,
            pid=pid,
            score=score,
        )

    async def get_latest_scores_by_user(self, user_id: uuid.UUID):
        async with self._session_factory() as session:
            stmt = (
                select(CharacterLadderScore)
                .where(CharacterLadderScore.user_id == user_id)
                .distinct(CharacterLadderScore.pid)
                .order_by(
                    CharacterLadderScore.pid,
                    CharacterLadderScore.recorded_at.desc(),
                )
            )
            result = await session.execute(stmt)
            scores = result.scalars().all()

        return {s.pid: s for s in scores}

    async def get_ladder_score_history(
        self,
        user_id: uuid.UUID,
        pid: int,
        *,
        limit: int = 100,
    ) -> Sequence[CharacterLadderScore]:
        """
        取得使用者某角色的認知分歷史。

        返回從最新到最舊的紀錄列表。
        """
        async with self._session_factory() as session:
            stmt = (
                select(CharacterLadderScore)
                .where(
                    CharacterLadderScore.user_id == user_id,
                    CharacterLadderScore.pid == pid,
                )
                .order_by(CharacterLadderScore.recorded_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return result.scalars().all()
