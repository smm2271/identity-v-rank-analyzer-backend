"""
Match Routes
=============
遊戲對戰紀錄上傳路由，使用 API Key 進行身分驗證。

═══════════════════════════════════════════════════
SOLID 原則對應
═══════════════════════════════════════════════════

(S) 單一職責
    本模組**僅**負責「對戰紀錄」相關的 HTTP 端點定義。
    - 路由函式只做請求解析 → 委派 Service → 回應組裝
    - 資料存取邏輯全部委派給 GameMatchService
    - DI 邏輯集中於 dependencies.py，本模組不自行管理

(O) 開放封閉
    MatchDetailResponse 繼承 MatchResponse 以擴展功能，
    若需新增欄位只擴展子類別，不修改基底 Schema。

(L) 里氏替換
    GameMatchService 繼承 BaseRepository[GameMatch]，
    保持與基底一致的介面行為，可安全替換。

(D) 依賴反轉
    所有 Service 透過 dependencies.py 的 getter 以 Depends() 注入，
    本模組**不直接 import AsyncSessionLocal 或建構任何 Service**。
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field

from database.service import GameMatchService, CharacterLadderScoreService
from routes.dependencies import get_match_service, get_ladder_score_service, verify_api_key

router = APIRouter(prefix="/matches", tags=["matches"])


# ──────────────────────────────────────────────
# Request / Response Schemas
# (S) 單一職責：每個 Schema 僅負責單一方向的資料驗證與序列化
# (O) 開閉原則：MatchDetailResponse 繼承 MatchResponse 擴展，不修改基底
# ──────────────────────────────────────────────

class PlayerInfoCreate(BaseModel):
    """單一玩家資訊（嵌入於對戰上傳請求中）"""

    player_id: int = Field(..., description="玩家 ID")
    player_name: Optional[str] = Field(None, max_length=14, description="玩家名稱")
    character_id: int = Field(..., description="角色 ID")
    res_type: Optional[int] = Field(None, description="逃脫狀態")


class LadderScoreInfo(BaseModel):
    """認知分資訊（場次相關的認知分變化）"""

    pid: int = Field(..., description="角色 ID")
    score: int = Field(..., description="當前認知分")


class MatchUploadRequest(BaseModel):
    """對戰紀錄上傳請求"""

    room_guuid: uuid.UUID = Field(..., description="房間 UUID")
    scene_id: Optional[int] = Field(None, description="地圖 ID")
    match_type: Optional[int] = Field(None, description="對戰類型 (1:排位, 2:匹配, 3:五人制)")
    rank_level: Optional[int] = Field(None, description="當時段位")
    kill_num: Optional[int] = Field(None, description="擊殺數")
    utype: Optional[int] = Field(None, description="角色類型 (1:監管 2:求生)")
    pid: Optional[int] = Field(None, description="我方角色 ID")
    game_save_time: Optional[datetime] = Field(None, description="遊戲結束時間")
    cipher_progress: Optional[Dict[str, Any]] = Field(None, description="各台密碼機修機進度")
    players: Optional[List[PlayerInfoCreate]] = Field(None, description="對局玩家資料")
    ladder_score_info: List[LadderScoreInfo] = Field(..., description="本場對局涉及的認知分更新（必填）")


class PlayerInfoResponse(BaseModel):
    """玩家資訊回應"""

    id: uuid.UUID
    player_id: int
    player_name: Optional[str]
    character_id: int
    res_type: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


class MatchResponse(BaseModel):
    """對戰紀錄回應"""

    id: uuid.UUID
    room_guuid: uuid.UUID
    uploader_id: uuid.UUID
    scene_id: Optional[int]
    match_type: Optional[int]
    rank_level: Optional[int]
    kill_num: Optional[int]
    utype: Optional[int]
    pid: Optional[int]
    game_save_time: Optional[datetime]
    cipher_progress: Optional[Dict[str, Any]]
    created_at: datetime

    model_config = {"from_attributes": True}


class MatchDetailResponse(MatchResponse):
    """
    包含玩家資訊的對戰紀錄回應。

    (O) 開閉原則：透過繼承 MatchResponse 擴展 players 欄位，
    而非修改基底 Schema。
    """

    players: List[PlayerInfoResponse] = []

    model_config = {"from_attributes": True}


class MatchListResponse(BaseModel):
    """對戰紀錄列表回應（含分頁資訊）"""

    total: int
    offset: int
    limit: int
    items: List[MatchResponse]


class CharacterLadderScoreResponse(BaseModel):
    """認知分紀錄回應"""

    id: uuid.UUID
    user_id: uuid.UUID
    pid: int
    score: int
    recorded_at: datetime

    model_config = {"from_attributes": True}


class LadderScoresListResponse(BaseModel):
    """認知分列表回應"""

    pid: int
    scores: List[CharacterLadderScoreResponse]


class LatestLadderScoresResponse(BaseModel):
    """最新認知分回應"""

    latest_scores: Dict[int, CharacterLadderScoreResponse]


# ──────────────────────────────────────────────
# Routes
# (S) 單一職責：路由函式僅負責 HTTP 層面的請求解析、回應組裝與錯誤處理，
#     資料存取邏輯全部委派給注入的 GameMatchService。
# (D) 依賴反轉：透過 Depends(verify_api_key) 取得 user_id，
#     透過 Depends(get_match_service) 取得 Service，皆為抽象依賴。
# ──────────────────────────────────────────────

@router.post(
    "",
    response_model=MatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="上傳對戰紀錄",
    description="上傳一筆遊戲對戰紀錄，需包含認知分更新資訊。可透過 X-API-Key 或 Authorization Bearer 驗證。",
)
async def upload_match(
    body: MatchUploadRequest,
    user_id: uuid.UUID = Depends(verify_api_key),
    match_svc: GameMatchService = Depends(get_match_service),
    ladder_svc: CharacterLadderScoreService = Depends(get_ladder_score_service),
):
    # 檢查是否已上傳過（room_guuid + uploader_id 唯一）
    existing = await match_svc.get_by_room_guuid(body.room_guuid, user_id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="此對戰紀錄已上傳過。",
        )

    players_data: Optional[List[Dict[str, Any]]] = None
    if body.players:
        players_data = [p.model_dump() for p in body.players]

    match = await match_svc.create_match(
        room_guuid=body.room_guuid,
        uploader_id=user_id,
        scene_id=body.scene_id,
        match_type=body.match_type,
        rank_level=body.rank_level,
        kill_num=body.kill_num,
        utype=body.utype,
        pid=body.pid,
        game_save_time=body.game_save_time,
        cipher_progress=body.cipher_progress,
        players=players_data,
    )

    # 保存認知分資訊
    if body.ladder_score_info:
        for ladder_info in body.ladder_score_info:
            await ladder_svc.create_ladder_score(
                user_id=user_id,
                pid=ladder_info.pid,
                score=ladder_info.score,
            )

    return match


@router.get(
    "",
    response_model=MatchListResponse,
    summary="取得我的對戰紀錄列表",
    description="取得當前使用者上傳的所有對戰紀錄（分頁）。可透過 X-API-Key 或 Authorization Bearer 驗證。",
)
async def list_my_matches(
    offset: int = 0,
    limit: int = 50,
    user_id: uuid.UUID = Depends(verify_api_key),
    match_svc: GameMatchService = Depends(get_match_service),
):
    total = await match_svc.count_by_uploader(user_id)
    items = await match_svc.get_matches_by_uploader(
        user_id, offset=offset, limit=limit
    )
    return MatchListResponse(
        total=total,
        offset=offset,
        limit=limit,
        items=[MatchResponse.model_validate(m) for m in items],
    )


@router.get(
    "/{match_id}",
    response_model=MatchDetailResponse,
    summary="取得對戰紀錄詳情",
    description="取得單筆對戰紀錄（含玩家資訊）。可透過 X-API-Key 或 Authorization Bearer 驗證，且僅能查看自己上傳的紀錄。",
)
async def get_match_detail(
    match_id: uuid.UUID,
    user_id: uuid.UUID = Depends(verify_api_key),
    match_svc: GameMatchService = Depends(get_match_service),
):
    match = await match_svc.get_with_players(match_id)
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="對戰紀錄不存在。",
        )

    # 僅允許上傳者查看自己的紀錄
    if match.uploader_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="無權查看此對戰紀錄。",
        )

    return MatchDetailResponse(
        **MatchResponse.model_validate(match).model_dump(),
        players=[PlayerInfoResponse.model_validate(p) for p in match.player_infos],
    )


@router.get(
    "/ladder-scores/latest",
    response_model=LatestLadderScoresResponse,
    summary="取得最新認知分",
    description="取得當前使用者各角色最新的認知分紀錄。可透過 X-API-Key 或 Authorization Bearer 驗證。",
)
async def get_latest_ladder_scores(
    user_id: uuid.UUID = Depends(verify_api_key),
    ladder_svc: CharacterLadderScoreService = Depends(get_ladder_score_service),
):
    """
    獲取使用者所有角色最新的認知分。
    返回格式: {pid: {id, user_id, pid, score, recorded_at}, ...}
    """
    latest_scores = await ladder_svc.get_latest_scores_by_user(user_id)

    # 轉換為回應格式
    result = {}
    for pid, score_record in latest_scores.items():
        result[pid] = CharacterLadderScoreResponse.model_validate(score_record)

    return LatestLadderScoresResponse(latest_scores=result)


@router.get(
    "/ladder-scores/{pid}",
    response_model=LadderScoresListResponse,
    summary="取得認知分歷史",
    description="取得當前使用者指定角色的認知分變化歷史（最新優先）。可透過 X-API-Key 或 Authorization Bearer 驗證。",
)
async def get_ladder_score_history(
    pid: int = Path(..., description="角色 ID"),
    limit: int = Query(100, ge=1, le=500, description="最多回傳筆數"),
    user_id: uuid.UUID = Depends(verify_api_key),
    ladder_svc: CharacterLadderScoreService = Depends(get_ladder_score_service),
):
    """
    獲取使用者某個角色的認知分完整歷史。
    返回最多 limit 筆紀錄，按時間倒序（最新優先）。
    """
    scores = await ladder_svc.get_ladder_score_history(
        user_id=user_id,
        pid=pid,
        limit=limit,
    )

    return LadderScoresListResponse(
        pid=pid,
        scores=[CharacterLadderScoreResponse.model_validate(s) for s in scores],
    )
