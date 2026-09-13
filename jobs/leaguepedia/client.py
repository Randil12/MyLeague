"""Client Leaguepedia (API MediaWiki/Cargo via mwrogue).

Authentification par Bot Password (Special:BotPasswords) :
LEAGUEPEDIA_USERNAME au format "Utilisateur@NomDuBot", LEAGUEPEDIA_PASSWORD = token.
Les imports mwrogue sont paresseux pour que les tests unitaires n'exigent pas la dépendance.
"""

from __future__ import annotations

import logging
import os
import time
from threading import Lock
from typing import Any

_cargo_lock = Lock()
_next_cargo_at = 0.0
_logger = logging.getLogger(__name__)


def paced_query(client, **kwargs):
    """Pace pages, probes and retries in the sole scheduled collector process.

    Other machines or independently launched processes are not covered.
    """
    global _next_cargo_at
    with _cargo_lock:
        for attempt in range(4):
            delay = _next_cargo_at - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            try:
                return client.cargo_client.query(**kwargs)
            except Exception as exc:
                if getattr(exc, "code", None) != "ratelimited" or attempt == 3:
                    raise
                cooldown = 60 * (2 ** attempt)
                _logger.warning("Cargo rate limited; waiting %s seconds before retry", cooldown)
                _next_cargo_at = time.monotonic() + cooldown
            finally:
                _next_cargo_at = max(_next_cargo_at, time.monotonic() + 2.0)


class LeaguepediaError(RuntimeError):
    pass


class PaginationLimit(LeaguepediaError):
    """The caller must split its time window instead of accepting truncated data."""


def get_credentials() -> tuple[str, str]:
    username = os.getenv("LEAGUEPEDIA_USERNAME")
    password = os.getenv("LEAGUEPEDIA_PASSWORD")
    if not username or not password:
        raise LeaguepediaError(
            "LEAGUEPEDIA_USERNAME / LEAGUEPEDIA_PASSWORD manquants. "
            "Créer un Bot Password sur https://lol.fandom.com/wiki/Special:BotPasswords"
        )
    return username, password


def get_client():
    from mwrogue.auth_credentials import AuthCredentials
    from mwrogue.esports_client import EsportsClient

    username, password = get_credentials()
    credentials = AuthCredentials(username=username, password=password)
    return EsportsClient("lol", credentials=credentials)


def cargo_query(
    client,
    tables: str,
    fields: str,
    where: str | None = None,
    order_by: str | None = None,
    page_size: int = 500,
    max_pages: int = 10,
    strict: bool = False,
) -> list[dict[str, Any]]:
    """Requête Cargo paginée (limite serveur : 500 lignes par page)."""
    if max_pages < 1:
        raise ValueError("max_pages must be positive")
    results: list[dict[str, Any]] = []
    for page in range(max_pages):
        kwargs: dict[str, Any] = {
            "tables": tables,
            "fields": fields,
            "limit": page_size,
            "offset": page * page_size,
        }
        if where:
            kwargs["where"] = where
        if order_by:
            kwargs["order_by"] = order_by
        rows = paced_query(client, **kwargs)
        results.extend(rows)
        if len(rows) < page_size:
            return results
    if strict:
        kwargs["offset"] = max_pages * page_size
        kwargs["limit"] = 1
        if paced_query(client, **kwargs):
            raise PaginationLimit(f"Window exceeds {max_pages} pages in {tables}")
    return results


def fetch_tournaments(client, year: int, max_pages: int = 4) -> list[dict[str, Any]]:
    return cargo_query(
        client,
        tables="Tournaments",
        fields="Name,OverviewPage,Region,League,DateStart,Date,Year,TournamentLevel,IsOfficial",
        where=f'Year="{year}"',
        max_pages=max_pages,
    )


def fetch_teams(client, max_pages: int = 10) -> list[dict[str, Any]]:
    return cargo_query(
        client,
        tables="Teams",
        fields="Name,OverviewPage,Short,Region,Location,IsDisbanded",
        where="IsDisbanded=0",
        max_pages=max_pages,
    )


def fetch_players(client, max_pages: int = 20) -> list[dict[str, Any]]:
    # SoloqueueIds : Riot ID des comptes solo queue des pros — permet de les
    # enregistrer comme joueurs suivis et d'ingérer leurs parties ladder
    # via le pipeline Riot existant ("Probuilds maison").
    return cargo_query(
        client,
        tables="Players",
        fields="ID,OverviewPage,Name,Country,Role,Team,SoloqueueIds,IsRetired",
        where="IsRetired=0",
        max_pages=max_pages,
    )


def fetch_scoreboard_players(
    client, since_iso: str, max_pages: int = 20, until_iso: str | None = None,
) -> list[dict[str, Any]]:
    """Stats individuelles par partie pro : qui a joué quel champion, à quel poste."""
    return cargo_query(
        client,
        tables="ScoreboardPlayers",
        fields=(
            "GameId,Link,Champion,Role,Side,Team,Kills,Deaths,Assists,"
            "CS,Gold,SummonerSpells,DateTime_UTC"
        ),
        where=f'DateTime_UTC >= "{since_iso}"' + (
            f' AND DateTime_UTC < "{until_iso}"' if until_iso else ""
        ),
        order_by="DateTime_UTC,GameId,Link",
        max_pages=max_pages,
        strict=until_iso is not None,
    )


def fetch_scoreboard_games(
    client, since_iso: str, max_pages: int = 20, until_iso: str | None = None,
) -> list[dict[str, Any]]:
    """Parties professionnelles (picks, bans, vainqueur, patch) depuis une date UTC."""
    return cargo_query(
        client,
        tables="ScoreboardGames",
        fields=(
            "GameId,MatchId,OverviewPage,Tournament,Team1,Team2,WinTeam,LossTeam,"
            "DateTime_UTC,Patch,Team1Picks,Team2Picks,Team1Bans,Team2Bans,"
            "Team1Kills,Team2Kills,Gamelength"
        ),
        where=f'DateTime_UTC >= "{since_iso}"' + (
            f' AND DateTime_UTC < "{until_iso}"' if until_iso else ""
        ),
        order_by="DateTime_UTC,GameId",
        max_pages=max_pages,
        strict=until_iso is not None,
    )
