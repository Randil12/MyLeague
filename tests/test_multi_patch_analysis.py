"""Tests des calculs purs de l'analyse multi-patch."""

from __future__ import annotations

import numpy as np

from analysis.multi_patch_analysis import bootstrap_median_difference


def test_bootstrap_median_difference_is_reproducible():
    changed = np.array([0.10, 0.20, 0.30])
    control = np.array([0.01, 0.02, 0.03, 0.04])

    first = bootstrap_median_difference(changed, control, iterations=500, seed=7)
    second = bootstrap_median_difference(changed, control, iterations=500, seed=7)

    assert first == second
    assert first[1] > 0


def test_bootstrap_interval_contains_zero_for_identical_samples():
    sample = np.array([0.01, 0.02, 0.03, 0.04, 0.05])
    low, high = bootstrap_median_difference(sample, sample, iterations=1000, seed=9)

    assert low <= 0 <= high
