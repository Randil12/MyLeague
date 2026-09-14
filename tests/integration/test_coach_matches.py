"""Roster -> simulated Riot -> real MinIO and raw PostgreSQL."""
from copy import deepcopy

from jobs.riot import coach_matches, live_roster


def test_added_player_matches_reach_raw_without_ladder(infrastructure, monkeypatch, tmp_path):
    conn, s3 = infrastructure
    with conn, conn.cursor() as cur:
        live_roster.init_roster(cur)
        cur.execute("INSERT INTO raw.riot_live_roster(puuid,riot_id) VALUES ('ci-coach-recent','CoachRecent#EUW')")
        live_roster.register_live_identity(cur, 'ci-coach-recent', 'CoachRecent#EUW')
        cur.execute("SELECT payload FROM raw.riot_matches WHERE match_id='CI_1'")
        payload = deepcopy(cur.fetchone()[0])
    payload['metadata'] = {'matchId':'EUW1_CICOACH'}
    payload['info']['participants'][0]['puuid'] = 'ci-coach-recent'
    monkeypatch.setattr(coach_matches.time, 'sleep', lambda _:None)
    monkeypatch.setattr(coach_matches.ingest, 'get_match_ids_by_puuid',
                        lambda player, **kwargs: ['EUW1_CICOACH'] if player=='ci-coach-recent' else [])
    downloads = []

    def get_match(match):
        downloads.append(match)
        return payload

    monkeypatch.setattr(coach_matches.ingest, 'get_match', get_match)
    monkeypatch.setattr(coach_matches.ingest, 'get_match_timeline',
                        lambda _: {'metadata':{'matchId':'EUW1_CICOACH'},'info':{'frames':[]}})
    try:
        result = coach_matches.run(tmp_path)
        assert result['loaded_to_raw'] == 1 and result['timelines_loaded_to_raw'] == 1
        assert coach_matches.run(tmp_path)['matches_downloaded'] == 0
        assert downloads == ['EUW1_CICOACH']
        with conn, conn.cursor() as cur:
            cur.execute("SELECT payload->'info'->'participants'->0->>'puuid' FROM raw.riot_matches WHERE match_id='EUW1_CICOACH'")
            assert cur.fetchone() == ('ci-coach-recent',)
        assert s3.list_objects_v2(Bucket='ci-live', Prefix='bronze/riot/region=euw1/matches/match_id=EUW1_CICOACH/')['KeyCount'] == 1
    finally:
        with conn, conn.cursor() as cur:
            cur.execute("DELETE FROM raw.riot_live_roster WHERE puuid='ci-coach-recent'")
