import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from database.model import CharacterLadderScore, GameMatch, PlayerInfo
from database.service import GameMatchService, UserService


@pytest_asyncio.fixture
async def test_user(session_factory):
    user_svc = UserService(session_factory)
    return await user_svc.create_user(
        username="uploader",
        email="uploader@example.com",
        agreed_to_terms_at=datetime.now(timezone.utc).replace(tzinfo=None)
    )


@pytest.mark.asyncio
async def test_create_match_atomicity(session_factory, test_user):
    match_svc = GameMatchService(session_factory)
    
    room_guuid = uuid.uuid4()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    
    players_data = [
        {"player_id": 1, "character_id": 1001, "player_name": "P1"},
        {"player_id": 2, "character_id": 2001, "player_name": "P2"}
    ]
    ladder_scores_data = [
        {"pid": 1001, "score": 5000}
    ]
    
    match = await match_svc.create_match(
        room_guuid=room_guuid,
        uploader_id=test_user.id,
        scene_id=1,
        match_type=2,
        rank_level=5,
        kill_num=4,
        utype=1,
        pid=1001,
        game_save_time=now,
        cipher_progress={"1": 100},
        players=players_data,
        ladder_scores=ladder_scores_data
    )
    
    assert match is not None
    assert match.id is not None
    assert match.room_guuid == room_guuid
    
    # Verify related data was inserted
    fetched_match = await match_svc.get_with_players(match.id)
    assert fetched_match is not None
    assert len(fetched_match.player_infos) == 2
    
    # Check ladder scores in DB manually since service doesn't fetch them attached to match
    async with session_factory() as session:
        result = await session.execute(
            select(CharacterLadderScore).where(CharacterLadderScore.user_id == test_user.id)
        )
        scores = result.scalars().all()
        assert len(scores) == 1
        assert scores[0].pid == 1001
        assert scores[0].score == 5000


@pytest.mark.asyncio
async def test_create_match_duplicate(session_factory, test_user):
    match_svc = GameMatchService(session_factory)
    room_guuid = uuid.uuid4()
    
    await match_svc.create_match(
        room_guuid=room_guuid,
        uploader_id=test_user.id
    )
    
    # Trying to upload the same room_guuid by the same uploader should fail
    # Note: SQLAlchemy raises IntegrityError for unique constraint violation
    from sqlalchemy.exc import IntegrityError
    
    with pytest.raises(IntegrityError):
        await match_svc.create_match(
            room_guuid=room_guuid,
            uploader_id=test_user.id
        )


@pytest.mark.asyncio
async def test_get_matches_by_uploader(session_factory, test_user):
    match_svc = GameMatchService(session_factory)
    
    # Create 3 matches
    for _ in range(3):
        await match_svc.create_match(
            room_guuid=uuid.uuid4(),
            uploader_id=test_user.id
        )
        
    matches = await match_svc.get_matches_by_uploader(test_user.id, limit=2)
    assert len(matches) == 2
    
    count = await match_svc.count_by_uploader(test_user.id)
    assert count == 3
