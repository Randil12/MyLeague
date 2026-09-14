"""Fixed proxy to private training storage. No write grant for the web role."""
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query

from backend.live_roster import forward, require_action
from jobs.riot.training import validate

router = APIRouter(prefix='/api/training')


@router.get('')
def goals(player: Annotated[str, Query(min_length=1, max_length=256)]):
    return forward('POST', '/training', {'action':'list', 'player':player})


@router.post('')
def change(body: dict, x_myleague_action: str = Header(default='')):
    require_action(x_myleague_action)
    try:
        validate(body)
    except (ValueError, KeyError, TypeError):
        raise HTTPException(422, 'Objectif ou séance invalide : vérifie les champs et la période.') from None
    return forward('POST', '/training', body)
