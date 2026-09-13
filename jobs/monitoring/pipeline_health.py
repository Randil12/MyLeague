"""Détection de pipelines en échec ou trop anciens et notification optionnelle."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from urllib.request import Request, urlopen

import psycopg2
from psycopg2.extras import RealDictCursor

PIPELINE_MAX_AGE_HOURS = {
    "datadragon_ingestion": 30,
    "riot_euw_ingestion": 30,
    "dbt_transform": 30,
    "leaguepedia_ingestion": 30,
    "patch_notes_scraping": 30,
    "riot_academy_tracking": 30,
    "riot_live_spectator": 1,
}
HEALTHY_STATUSES = {"success", "partial_success", "scraped", "already_ingested"}


def get_connection():
    return psycopg2.connect(
        host=os.getenv("GOLD_POSTGRES_HOST", "gold-postgres"),
        port=int(os.getenv("GOLD_POSTGRES_PORT", "5432")),
        dbname=os.getenv("GOLD_POSTGRES_DB", "gold"),
        user=os.getenv("GOLD_POSTGRES_USER", "gold"),
        password=os.getenv("GOLD_POSTGRES_PASSWORD", "gold"),
    )


def evaluate_pipeline_health(
    latest_runs: dict[str, dict[str, Any]],
    now: datetime | None = None,
    thresholds: dict[str, int] | None = None,
) -> list[dict[str, str]]:
    """Retourne une alerte par pipeline absent, en échec ou trop ancien."""
    current_time = now or datetime.now(timezone.utc)
    limits = thresholds or PIPELINE_MAX_AGE_HOURS
    alerts: list[dict[str, str]] = []

    for pipeline_name, max_age_hours in limits.items():
        run = latest_runs.get(pipeline_name)
        if run is None:
            alerts.append(
                {
                    "pipeline_name": pipeline_name,
                    "alert_type": "missing_run",
                    "severity": "critical",
                    "message": "Aucune exécution enregistrée.",
                }
            )
            continue

        status = str(run.get("status") or "unknown").lower()
        if status not in HEALTHY_STATUSES:
            alerts.append(
                {
                    "pipeline_name": pipeline_name,
                    "alert_type": "failed_run",
                    "severity": "critical",
                    "message": f"Dernier statut non sain : {status}.",
                }
            )
            continue

        started_at = run.get("started_at")
        if not isinstance(started_at, datetime):
            alerts.append(
                {
                    "pipeline_name": pipeline_name,
                    "alert_type": "invalid_timestamp",
                    "severity": "warning",
                    "message": "Horodatage de la dernière exécution invalide.",
                }
            )
            continue

        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        age_hours = (current_time - started_at).total_seconds() / 3600
        if age_hours > max_age_hours:
            alerts.append(
                {
                    "pipeline_name": pipeline_name,
                    "alert_type": "stale_run",
                    "severity": "warning",
                    "message": (
                        f"Dernière exécution vieille de {age_hours:.1f} h "
                        f"(seuil {max_age_hours} h)."
                    ),
                }
            )

    return alerts


def send_webhook(alerts: list[dict[str, str]], webhook_url: str) -> None:
    payload = json.dumps(
        {
            "text": "MyLeague — nouvelles alertes pipelines",
            "alerts": alerts,
        }
    ).encode("utf-8")
    request = Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:  # noqa: S310 - URL explicitement configurée
        if response.status >= 400:
            raise RuntimeError(f"Webhook en échec avec le statut HTTP {response.status}")


def run() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    with get_connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (pipeline_name)
                pipeline_name, status, started_at, ended_at, error_message
            FROM audit.pipeline_runs
            ORDER BY pipeline_name, started_at DESC
            """
        )
        latest_runs = {row["pipeline_name"]: dict(row) for row in cur.fetchall()}
        alerts = evaluate_pipeline_health(latest_runs, now=now)

        cur.execute(
            """
            SELECT pipeline_name, alert_type, notification_sent
            FROM audit.pipeline_alerts
            WHERE resolved_at IS NULL
            """
        )
        active = {
            (row["pipeline_name"], row["alert_type"]): bool(row["notification_sent"])
            for row in cur.fetchall()
        }
        current_keys = {(a["pipeline_name"], a["alert_type"]) for a in alerts}

        for alert in alerts:
            cur.execute(
                """
                INSERT INTO audit.pipeline_alerts (
                    pipeline_name, alert_type, severity, message,
                    first_detected_at, last_detected_at, resolved_at, notification_sent
                )
                VALUES (%s, %s, %s, %s, %s, %s, NULL, FALSE)
                ON CONFLICT (pipeline_name, alert_type) DO UPDATE SET
                    severity = EXCLUDED.severity,
                    message = EXCLUDED.message,
                    last_detected_at = EXCLUDED.last_detected_at,
                    resolved_at = NULL
                """,
                (
                    alert["pipeline_name"],
                    alert["alert_type"],
                    alert["severity"],
                    alert["message"],
                    now,
                    now,
                ),
            )

        for pipeline_name, alert_type in set(active) - current_keys:
            cur.execute(
                """
                UPDATE audit.pipeline_alerts
                SET resolved_at = %s
                WHERE pipeline_name = %s AND alert_type = %s
                """,
                (now, pipeline_name, alert_type),
            )

        to_notify = [
            alert
            for alert in alerts
            if not active.get((alert["pipeline_name"], alert["alert_type"]), False)
        ]
        webhook_url = os.getenv("ALERT_WEBHOOK_URL", "").strip()
        notified = False
        if webhook_url and to_notify:
            send_webhook(to_notify, webhook_url)
            notified = True
            for alert in to_notify:
                cur.execute(
                    """
                    UPDATE audit.pipeline_alerts
                    SET notification_sent = TRUE
                    WHERE pipeline_name = %s AND alert_type = %s
                    """,
                    (alert["pipeline_name"], alert["alert_type"]),
                )

    return {
        "checked_at": now.isoformat(),
        "pipeline_count": len(PIPELINE_MAX_AGE_HOURS),
        "active_alerts": len(alerts),
        "new_alerts": len(to_notify),
        "webhook_notified": notified,
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False))

