"""`packaging/compare_growthrates.py` makes the counts `grownet.rates` states about the reference; these are
its classes, each a claim a reader can check, decided without R (found in review: the counts were made by
hand, on a selection nobody wrote down, and went stale twice)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packaging"))
from compare_growthrates import CLASSES, classify  # noqa: E402

NO_SEGMENT = "no positively growing segment of length h >= 5  found"


def test_each_curve_falls_in_the_class_the_rates_docstring_names():
    assert classify(0.4, "", 0.4, "") == "both"
    assert classify(None, "too few points", None, "h must be > 1 and < N") == "neither"
    # the shape the real `neither` curves have (round 14 of the review): R refuses a value <= 0 and grownet
    # has too few positive points left, which is not departure 1, since no refit was made
    assert classify(None, "5 positive time point(s); easylinear with a window of 5 needs 6", None,
                    "dependent variable y must be positive") == "neither"
    # a refit with no value <= 0 behind it is not departure 2+1 either, whatever R said instead
    refit = "the steepest window rises at 0.1 per time unit, but the refit ... falls to"
    assert classify(None, refit, None, "h must be > 1 and < N") == "neither"
    assert classify(None, refit, None, "no answer from R") == "neither"
    # 1: the steepest window rose and grownet's refit fell to or below zero; R returns the negative number
    assert classify(None, "the steepest window rises at 0.102 per time unit, but the refit ... falls to", -0.01218,
                    "") == "departure 1"
    # 2: R refuses any value <= 0; grownet drops those points and fits
    assert classify(0.3, "", None, "dependent variable y must be positive") == "departure 2"
    # 2 then 1: R refuses the values <= 0, and grownet's refit over what remains falls <= 0
    assert classify(None, "the steepest window rises at 0.1 per time unit, but the refit ... falls to", None,
                    "dependent variable y must be positive") == "departure 2+1"
    # 3: no rising window; R fits nothing, grownet returns its slope, <= 0
    assert classify(-0.002, "", None, NO_SEGMENT) == "departure 3"
    assert classify(0.0, "", None, NO_SEGMENT) == "departure 3", "a flat curve's slope is 0, which is <= 0"


def test_a_departure_nobody_named_is_other_which_fails_the_comparison():
    assert classify(None, "some new reason", 0.4, "") == "other"         # R fits, grownet not, not a refit
    assert classify(None, "too few points", -0.5, "") == "other"         # a negative R rate needs the refit
    assert classify(0.4, "", None, NO_SEGMENT) == "other"                # a positive rate where R finds none
    assert classify(0.4, "", None, "something else") == "other"
    assert "other" in CLASSES


def test_every_class_a_curve_can_fall_in_is_one_the_table_prints():
    """Round 14 of the review: a class missing from CLASSES dropped its curves from the table, which then
    summed to 465 of 468 and exited 0."""
    import compare_growthrates
    cases = [(0.4, "", 0.4, ""), (None, "x", None, ""), (None, "refit", -0.1, ""),
             (0.3, "", None, "dependent variable y must be positive"),
             (None, "refit", None, "dependent variable y must be positive"), (-0.1, "", None, NO_SEGMENT),
             (0.4, "", None, "x")]
    assert {classify(*case) for case in cases} == set(CLASSES)
    assert compare_growthrates.table_complete({("both", "strain"): 2, ("neither", "strain"): 1}, 3)
    assert not compare_growthrates.table_complete({("both", "strain"): 2}, 3)
    assert not compare_growthrates.table_complete({("unlisted", "strain"): 3}, 3)
