from datetime import datetime, timedelta, timezone

from jobs.monitoring.pipeline_health import evaluate_pipeline_health


def test_health_detects_missing_failed_and_stale_runs():
    now = datetime(2026, 7, 25, 12, tzinfo=timezone.utc)
    runs = {
        "failed": {"status": "failed", "started_at": now},
        "stale": {"status": "success", "started_at": now - timedelta(hours=3)},
    }
    alerts = evaluate_pipeline_health(
        runs,
        now=now,
        thresholds={"missing": 1, "failed": 1, "stale": 1},
    )
    assert {(a["pipeline_name"], a["alert_type"]) for a in alerts} == {
        ("missing", "missing_run"),
        ("failed", "failed_run"),
        ("stale", "stale_run"),
    }


def test_health_accepts_recent_success_and_partial_success():
    now = datetime(2026, 7, 25, 12, tzinfo=timezone.utc)
    runs = {
        "daily": {"status": "success", "started_at": now - timedelta(hours=4)},
        "partial": {
            "status": "partial_success",
            "started_at": now - timedelta(hours=2),
        },
    }
    assert evaluate_pipeline_health(
        runs,
        now=now,
        thresholds={"daily": 30, "partial": 30},
    ) == []

