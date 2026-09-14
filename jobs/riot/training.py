"""Private staff training plans; writes stay in the internal service, not web SQL."""
import math
from datetime import date

METRICS = {'gd_15', 'xpd_15', 'cs_min', 'damage_min', 'solo_deaths_15'}


def init_training(cur):
    cur.execute('CREATE SCHEMA IF NOT EXISTS app')
    cur.execute("""CREATE TABLE IF NOT EXISTS app.training_goals (
        id bigserial PRIMARY KEY, puuid text NOT NULL, title text NOT NULL,
        metric text NOT NULL, threshold double precision NOT NULL,
        champion text NOT NULL DEFAULT '', role text NOT NULL DEFAULT '',
        starts_on date NOT NULL, ends_on date NOT NULL,
        status text NOT NULL DEFAULT 'active' CHECK(status IN ('active','completed','archived')),
        created_at timestamptz NOT NULL DEFAULT now(), CHECK(ends_on>=starts_on)
    );
    CREATE INDEX IF NOT EXISTS training_goals_player ON app.training_goals(puuid,id);
    CREATE TABLE IF NOT EXISTS app.training_sessions (
        id bigserial PRIMARY KEY, goal_id bigint NOT NULL REFERENCES app.training_goals(id),
        played_on date NOT NULL, notes text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS training_sessions_goal ON app.training_sessions(goal_id,id)""")


def validate(body):
    if not isinstance(body, dict):
        raise ValueError('Requête invalide')
    action = body.get('action')
    if action not in {'list', 'create', 'status', 'session'}:
        raise ValueError('Action inconnue')
    if not isinstance(body.get('player'), str) or not 1 <= len(body['player']) <= 256:
        raise ValueError('Joueur invalide')
    if action == 'create':
        for field, limit in [('title', 160), ('champion', 100), ('role', 16)]:
            if not isinstance(body.get(field), str) or len(body[field]) > limit:
                raise ValueError('Texte invalide')
        if not body['title'].strip() or body.get('metric') not in METRICS:
            raise ValueError('Objectif invalide')
        if body['role'] not in {'', 'TOP', 'JUNGLE', 'MIDDLE', 'BOTTOM', 'UTILITY'}:
            raise ValueError('Rôle invalide')
        threshold = body.get('threshold')
        if type(threshold) not in (int, float) or not math.isfinite(threshold) or abs(threshold) > 100000:
            raise ValueError('Seuil invalide')
        if body['metric'] not in {'gd_15', 'xpd_15'} and threshold < 0:
            raise ValueError('Seuil négatif invalide')
        start, end = date.fromisoformat(body['starts_on']), date.fromisoformat(body['ends_on'])
        if not 0 <= (end-start).days <= 366:
            raise ValueError('Période invalide (maximum 366 jours)')
    if action in {'status', 'session'} and (type(body.get('id')) is not int or body['id'] <= 0):
        raise ValueError('Identifiant invalide')
    if action == 'status' and body.get('status') not in {'active', 'completed', 'archived'}:
        raise ValueError('Statut invalide')
    if action == 'session':
        date.fromisoformat(body['played_on'])
        if not isinstance(body.get('notes'), str) or not 1 <= len(body['notes'].strip()) <= 2000:
            raise ValueError('Note invalide (1 à 2000 caractères)')
    return body


def request(cur, body):
    b = validate(body)
    cur.execute('SELECT 1 FROM raw.riot_live_roster WHERE puuid=%s', (b['player'],))
    if not cur.fetchone():
        raise ValueError('Choisis un joueur actuellement suivi')
    if b['action'] == 'create':
        cur.execute("""INSERT INTO app.training_goals
            (puuid,title,metric,threshold,champion,role,starts_on,ends_on)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            tuple(b[k] for k in ['player','title','metric','threshold','champion','role','starts_on','ends_on']))
        return {'id': cur.fetchone()[0]}
    if b['action'] in {'status', 'session'}:
        cur.execute('SELECT starts_on,ends_on FROM app.training_goals WHERE id=%s AND puuid=%s FOR UPDATE',
                    (b['id'], b['player']))
        goal = cur.fetchone()
        if not goal:
            raise ValueError('Objectif introuvable pour ce joueur')
        if b['action'] == 'status':
            cur.execute('UPDATE app.training_goals SET status=%s WHERE id=%s', (b['status'],b['id']))
        else:
            if not goal[0] <= date.fromisoformat(b['played_on']) <= goal[1]:
                raise ValueError('La séance doit être dans la période de l’objectif')
            cur.execute('INSERT INTO app.training_sessions(goal_id,played_on,notes) VALUES (%s,%s,%s)',
                        (b['id'], b['played_on'], b['notes'].strip()))
        return {'ok': True}
    # Metrics are selected by CASE, never interpolated from client input.
    cur.execute("""SELECT g.id,g.title,g.metric,g.threshold,g.champion,g.role,
        g.starts_on::text,g.ends_on::text,g.status,
        p.games,p.evaluated,p.success,p.mean,
        COALESCE((SELECT json_agg(json_build_object('id',s.id,'played_on',s.played_on,
            'notes',s.notes) ORDER BY s.played_on DESC,s.id DESC)
            FROM app.training_sessions s WHERE s.goal_id=g.id),'[]'::json) AS sessions
        FROM app.training_goals g
        LEFT JOIN LATERAL (
            SELECT count(*) AS games,count(value) AS evaluated,avg(value) AS mean,
                count(*) FILTER(WHERE CASE WHEN g.metric='solo_deaths_15'
                    THEN value<=g.threshold ELSE value>=g.threshold END) AS success
            FROM (SELECT CASE g.metric WHEN 'gd_15' THEN l.gd_15
                WHEN 'xpd_15' THEN l.xpd_15 WHEN 'cs_min' THEN l.cs_min
                WHEN 'damage_min' THEN l.damage_min WHEN 'solo_deaths_15' THEN l.solo_deaths_15 END AS value
                FROM gold.gold_player_lane l WHERE l.puuid=g.puuid
                AND l.game_started_at >= g.starts_on::timestamp AT TIME ZONE 'UTC'
                AND l.game_started_at < (g.ends_on+1)::timestamp AT TIME ZONE 'UTC'
                AND (g.champion='' OR l.champion_name=g.champion)
                AND (g.role='' OR l.role=g.role)) measured
        ) p ON true WHERE g.puuid=%s ORDER BY g.id DESC""", (b['player'],))
    columns = [d[0] for d in cur.description]
    rows = [dict(zip(columns, r)) for r in cur.fetchall()]
    for row in rows:
        row['mean'] = float(row['mean']) if row['mean'] is not None else None
    return rows
