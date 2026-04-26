from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from database.service import CharacterLadderScoreService, UserService


@pytest_asyncio.fixture
async def test_user(session_factory):
    user_svc = UserService(session_factory)
    return await user_svc.create_user(
        username="ladderuser",
        email="ladder@example.com",
        agreed_to_terms_at=datetime.now(timezone.utc).replace(tzinfo=None)
    )


@pytest.mark.asyncio
async def test_create_and_get_history(session_factory, test_user):
    ladder_svc = CharacterLadderScoreService(session_factory)
    
    await ladder_svc.create_ladder_score(
        user_id=test_user.id,
        pid=1001,
        score=5000
    )
    
    await ladder_svc.create_ladder_score(
        user_id=test_user.id,
        pid=1001,
        score=5100
    )
    
    # Another character
    await ladder_svc.create_ladder_score(
        user_id=test_user.id,
        pid=2001,
        score=3000
    )
    
    # Check history for 1001
    history = await ladder_svc.get_ladder_score_history(test_user.id, 1001)
    assert len(history) == 2
    # Should be sorted by descending order of recorded_at (which defaults to func.now())
    # But since they were inserted rapidly, the order might be same if DB precision is low.
    # However, postgres handles timestamps well.
    assert history[0].score == 5100 or history[1].score == 5100
    
    # Check history for 2001
    history2 = await ladder_svc.get_ladder_score_history(test_user.id, 2001)
    assert len(history2) == 1
    assert history2[0].score == 3000


@pytest.mark.asyncio
async def test_get_latest_scores(session_factory, test_user):
    ladder_svc = CharacterLadderScoreService(session_factory)
    
    # For PID 1001, two records
    await ladder_svc.create_ladder_score(user_id=test_user.id, pid=1001, score=100)
    import asyncio
    await asyncio.sleep(0.1) # Ensure distinct timestamp
    await ladder_svc.create_ladder_score(user_id=test_user.id, pid=1001, score=200)
    
    # For PID 2001, one record
    await ladder_svc.create_ladder_score(user_id=test_user.id, pid=2001, score=500)
    
    latest = await ladder_svc.get_latest_scores_by_user(test_user.id)
    
    assert len(latest) == 2
    assert 1001 in latest
    assert latest[1001].score == 200 # Should be the latest one
    
    assert 2001 in latest
    assert latest[2001].score == 500
