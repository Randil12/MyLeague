"""Tests unitaires des fonctions pures du script de tests statistiques."""

from jobs.analytics.generate_statistical_report import decision, format_p


def test_format_p_thresholds():
    assert format_p(0.0000042) == "p < 0,001"
    assert format_p(0.042) == "p = 0,042"
    assert format_p(0.5) == "p = 0,500"


def test_decision_at_alpha():
    assert decision(0.049) == "H0 rejetée"
    assert decision(0.051) == "H0 non rejetée"
    assert decision(0.05) == "H0 non rejetée"  # seuil strict : p < alpha
