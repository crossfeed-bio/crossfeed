"""The reported statistics, checked against printed tables and hand-computed values."""
import math

import pytest

from crossfeed.stats import benjamini_hochberg, benjamini_yekutieli, incomplete_beta, t_cdf, welch


@pytest.mark.parametrize("df, critical", [(1, 12.706), (2, 4.303), (4, 2.776), (10, 2.228), (30, 2.042)])
def test_t_distribution_matches_printed_two_sided_critical_values(df, critical):
    assert 2 * (1 - t_cdf(critical, df)) == pytest.approx(0.05, abs=5e-4)


def test_t_distribution_is_symmetric_and_centered():
    assert t_cdf(0.0, 5) == pytest.approx(0.5)
    assert t_cdf(-1.3, 7) == pytest.approx(1 - t_cdf(1.3, 7))


def test_incomplete_beta_edge_values():
    assert incomplete_beta(2, 3, 0) == 0 and incomplete_beta(2, 3, 1) == 1
    # I_x(1, 1) = x (the uniform distribution)
    assert incomplete_beta(1, 1, 0.37) == pytest.approx(0.37)


def test_welch_on_a_hand_computed_example():
    # x: 1, 2, 3 (mean 2, var 1); y: 4, 6 (mean 5, var 2); se^2 = 1/3 + 2/2 = 4/3
    # df = (4/3)^2 / ((1/3)^2 / 2 + 1^2 / 1) = (16/9) / (1/18 + 1) = 32/19
    result = welch([1, 2, 3], [4, 6])
    assert result["t"] == pytest.approx(-3 / math.sqrt(4 / 3))
    assert result["df"] == pytest.approx(32 / 19)
    assert 0 < result["p"] < 1


def test_welch_needs_two_values_per_side():
    assert welch([1.0], [2.0, 3.0]) is None


def test_welch_without_spread():
    assert welch([1.0, 1.0], [2.0, 2.0])["p"] == 0.0
    assert welch([1.0, 1.0], [1.0, 1.0])["p"] == 1.0


def test_benjamini_hochberg_on_a_textbook_example():
    # p = 0.01, 0.04, 0.03, 0.005 (m = 4); sorted 0.005, 0.01, 0.03, 0.04 -> 0.02, 0.02, 0.04, 0.04
    assert benjamini_hochberg([0.01, 0.04, 0.03, 0.005]) == pytest.approx([0.02, 0.04, 0.04, 0.02])


def test_benjamini_hochberg_skips_untested_entries():
    adjusted = benjamini_hochberg([0.01, None, 0.04])
    assert adjusted[1] is None
    assert adjusted[0] == pytest.approx(0.02) and adjusted[2] == pytest.approx(0.04)


def test_benjamini_yekutieli_scales_by_the_harmonic_sum():
    # m = 4: c = 1 + 1/2 + 1/3 + 1/4 = 25/12; the Benjamini-Hochberg values 0.02, 0.04, 0.04, 0.02 times c
    c = 25 / 12
    assert benjamini_yekutieli([0.01, 0.04, 0.03, 0.005]) == pytest.approx([0.02 * c, 0.04 * c, 0.04 * c, 0.02 * c])
    assert benjamini_yekutieli([0.9, 0.95]) == pytest.approx([1.0, 1.0])       # capped at 1
    assert benjamini_yekutieli([0.01, None])[1] is None
