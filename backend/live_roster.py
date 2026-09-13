"""Proxy only fixed roster operations. The web database role remains read-only."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/live/roster")


class PlayerInput(BaseModel):
    riot_id: str = Field(min_length=3, max_length=64)


def forward(method, suffix="", data=None):
    base = os.getenv("RIOT_LIVE_SERVICE_URL", "http://riot-live:8091").rstrip("/")
    request = Request(base + "/roster" + suffix, method=method,
                      data=json.dumps(data).encode() if data is not None else None,
                      headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=75) as response:
            return json.load(response)
    except HTTPError as exc:
        try:
            detail = json.load(exc).get("detail", "Suivi indisponible.")
        except (ValueError, AttributeError):
            detail = "Suivi indisponible."
        raise HTTPException(exc.code, detail) from None
    except (URLError, TimeoutError, ValueError):
        raise HTTPException(503, "Service riot-live inaccessible. Vérifie son démarrage.") from None


def require_action(value):
    # Non-simple header prevents cross-origin HTML forms from mutating the private app.
    # No CORS middleware grants permission to other origins. Not a replacement for login.
    if value != "roster":
        raise HTTPException(403, "Action non autorisée.")


@router.get("")
def list_players():
    return forward("GET")


@router.post("")
def add_player(player: PlayerInput, x_myleague_action: str = Header(default="")):
    require_action(x_myleague_action)
    return forward("POST", data=player.model_dump())


@router.delete("/{player_id}")
def remove_player(player_id: int, x_myleague_action: str = Header(default="")):
    require_action(x_myleague_action)
    if player_id <= 0:
        raise HTTPException(422, "Identifiant invalide.")
    return forward("DELETE", suffix=f"/{player_id}")
