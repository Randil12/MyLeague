"""SELECT-only regression for first-letter variants and genuine homonyms."""
from pathlib import Path

from jinja2 import Template


def test_pro_identity(infrastructure):
    path = Path(__file__).resolve().parents[2] / 'dbt/models/gold/gold_pro_player_games.sql'
    sql = Template(path.read_text(encoding='utf-8')).render(
        config=lambda **kwargs: '', source=lambda schema, table: 'fixture_' + table)
    fixtures = """WITH fixture_leaguepedia_scoreboard_players AS (
        SELECT 'game1'::text AS game_id, page AS player_page,
            'Azir'::text AS champion, 'Mid'::text AS role,
            jsonb_build_object('Kills', kills::text) AS payload,
            '2026-01-01'::timestamptz + age * interval '1 hour' AS loaded_at
        FROM (VALUES ('beishang',1,0),('Beishang',2,1),
            ('Feng (Chen Chun-Feng)',3,0),('Feng (Jose Ricalday)',4,0)) v(page,kills,age)
    ), fixture_leaguepedia_players AS (
        SELECT 'Beishang'::text AS overview_page, '{"ID":"beishang"}'::jsonb AS payload,
            now() AS loaded_at
    ), fixture_leaguepedia_scoreboard_games AS (
        SELECT 'game1'::text AS game_id, '2026-01-01'::timestamptz AS game_date,
            '26.1'::text AS patch, '{}'::jsonb AS payload, now() AS loaded_at
    ), fixture_leaguepedia_tournaments AS (
        SELECT ''::text AS overview_page, '{}'::jsonb AS payload WHERE false
    ) SELECT player_page, kills FROM ("""
    with infrastructure[0].cursor() as cur:
        cur.execute(fixtures + sql + ') result')
        rows = dict(cur.fetchall())
    assert rows == {'Beishang': 2, 'Feng (Chen Chun-Feng)': 3, 'Feng (Jose Ricalday)': 4}
