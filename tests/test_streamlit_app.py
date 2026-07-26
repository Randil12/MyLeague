"""Smoke test de l'application métier en mode base indisponible."""

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_app_starts_in_degraded_mode_without_database(monkeypatch):
    """L'indisponibilité de PostgreSQL doit être expliquée, pas faire planter l'UI."""
    monkeypatch.setenv("GOLD_POSTGRES_HOST", "127.0.0.1")
    monkeypatch.setenv("GOLD_POSTGRES_PORT", "1")

    app_path = Path(__file__).parents[1] / "app" / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=10).run()

    assert not app.exception
    assert not app.error
    assert app.warning
    assert "Données indisponibles" in app.warning[0].value
