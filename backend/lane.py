"""Lane metrics for the current coach roster only."""
from typing import Annotated

from fastapi import APIRouter, Query

from backend import db

router = APIRouter(prefix='/api/lane')


@router.get('')
def lane(player: Annotated[str, Query(min_length=1, max_length=256)],
         patch: Annotated[str, Query(max_length=32)]):
    return db.query("""SELECT l.* FROM gold.gold_player_lane l
        JOIN gold.gold_coach_roster r ON r.puuid=l.puuid
        WHERE l.puuid=:player AND (:patch='' OR l.patch=:patch)
        ORDER BY l.game_started_at DESC, l.match_id DESC""",
        {'player':player,'patch':patch})
