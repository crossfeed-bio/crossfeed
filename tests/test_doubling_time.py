"""The doubling time printed beside every growth rate (#173).

No stage of the derivation asks whether a growth rate is plausible: the guards are identifiability, model
fit, growth above zero and the R2 gate against the interaction-free null, and a rate's magnitude is never
questioned. Craig's agent, on #173 (2026-10-08): publishing the implied doubling time "does not catch
anything automatically, but it converts an uninspectable number into an inspectable one". Karoline took it
the same day. So this is reporting, not a guard, and these tests check the number and that it reaches the
two files a reader reads.

Every number here is computed by hand: ln(2) = 0.693147.
"""
import csv
import io
import math

from grownet import matrix
from grownet.model import InteractionNetwork
from grownet.rates import doubling_time, time_unit
from grownet.report import report_text


def test_the_doubling_time_is_ln2_over_the_rate():
    # 0.2 /h: ln(2) / 0.2 = 3.4657 h. A 24-hour doubling is 0.028881 /h, so anything slower is below that
    assert doubling_time(0.2) == math.log(2) / 0.2
    assert round(doubling_time(0.2), 4) == 3.4657
    assert round(doubling_time(0.0147), 2) == 47.15        # the slowest live monoculture fit of #173
    assert round(doubling_time(0.8831), 4) == 0.7849       # and the fastest
    # the unit is the rate's own: nothing is converted behind the reader
    assert time_unit("1/h") == "h" and time_unit("1/day") == "day"
    assert doubling_time(0.2, "1/day") == doubling_time(0.2, "1/h")


def test_a_rate_that_cannot_double_anything_has_no_doubling_time():
    """A rate of 0 or below doubles nothing, and None is not a rate. The column is empty rather than
    holding an infinity or a negative time."""
    assert doubling_time(0) is None and doubling_time(None) is None and doubling_time(-0.3) is None
    rates = {"a": {"rate": 0.0, "unit": "1/h"}}
    table = list(csv.reader(io.StringIO(matrix.rates_csv(rates))))
    assert dict(zip(table[0], table[1], strict=True))["doubling_time"] == ""


def test_the_rates_file_prints_it_beside_the_rate():
    """ln(2) / 0.0147 = 47.15 h: the same fit, in the form that makes a reader stop."""
    rates = {"a": {"name": "Shewanella sp.", "rate": 0.0147, "unit": "1/h", "n": 3, "studies": ["S1"]}}
    table = list(csv.reader(io.StringIO(matrix.rates_csv(rates))))
    row = dict(zip(table[0], table[1], strict=True))
    assert row["growth_rate"] == "0.0147" and row["unit"] == "1/h"
    assert row["doubling_time"] == "47.15"


def test_the_report_prints_it_beside_the_rate():
    net = InteractionNetwork()
    net.meta["growth_rates"] = {"rule": "r", "organisms": {
        "a": {"name": "Shewanella sp.", "rate": 0.0147, "unit": "1/h", "n": 3, "per_study": {}},
        "b": {"name": "Escherichia coli", "rate": 0.8831, "unit": "1/h", "n": 3, "per_study": {}}}}
    text = report_text({"network": net, "resolved": [], "unresolved": [], "studies": [], "errors": [],
                        "skipped": [], "entries": []})
    assert "doubling 47.15 h" in text and "doubling 0.7849 h" in text
