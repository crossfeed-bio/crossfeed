"""The files a reader keeps from a gLV package describe themselves correctly once they leave the page
(#210, #211)."""
import csv
import io

from test_payload_v1 import PAIR, RATES, _arc, _net, _rate

from grownet import matrix


def test_a_censored_cell_is_named_only_where_it_is_in_a_matrix():
    """#211 item 2: the README listed cells "from a comparison where one side did not grow" as entering
    the median of their pair, for an organism WHAT IS NOT IN HERE lists as in no matrix."""
    arcs = PAIR + [_arc("c", "a", 0.8, 0.0, outcome="obligate", strength=None)]
    # C has a rate, so it is in the matrix and its censored cell is named
    kept = matrix.glv_payload(_net(arcs), {**RATES, "c": _rate("C", 0.5, 1.0e8)})
    assert kept["caveats"]["censored_cells"] == [{"affected": "A", "actor": "C"}]
    # C has none, so it is in no matrix, and its cell is named nowhere as if it were
    dropped = matrix.glv_payload(_net(arcs), RATES)
    assert "C" not in [o for block in dropped["matrices"] for o in block["organisms"]]
    assert dropped["caveats"]["censored_cells"] == []
    assert "ONE SIDE DID NOT GROW" not in dropped["readme"]


def test_the_rate_method_lines_are_the_derivation_s_own():
    """#211 item 1: a package built in gLV mode described its off-diagonals as fitted, then nineteen lines
    later as "its own comparison's two rates", and said a setting chooses the estimator that the
    integrated form does not read."""
    got = {"rate_methods": ["integrated: monoculture fit"], "lag_methods": []}
    integrated = "\n".join(matrix._rate_method_lines(got, "integrated"))
    assert "own comparison's two rates" not in integrated and "chooses it" not in integrated
    assert "not read by this" in integrated
    replicate = "\n".join(matrix._rate_method_lines({"rate_methods": ["easylinear"], "lag_methods": []}))
    assert "own comparison's two rates" in replicate and "chooses it" in replicate


def _rates_rows(rates):
    return list(csv.DictReader(io.StringIO(matrix.rates_csv(rates, _net(PAIR)))))


def test_zero_curves_left_out_is_written_as_zero_not_blank():
    """#211 item 5: `len(...) or ""` turned the count 0 into a blank, which R reads as NA, the cell the
    column exists to tell apart from "no capacity at all"."""
    rows = _rates_rows({"a": {**RATES["a"], "capacity_left_out": []},
                        "b": {**RATES["b"], "capacity_left_out": [["x", "no plateau"], ["y", "spiked"]]}})
    assert [r["capacity_curves_left_out"] for r in rows] == ["0", "2"]
    # and blank only where the derivation recorded nothing about it
    assert _rates_rows({"a": RATES["a"]})[0]["capacity_curves_left_out"] == ""


def test_a_nonzero_number_is_never_written_as_zero():
    """#211, the latent hazard: four decimal places print |v| < 5e-5 as `0` or `-0`, and `0` is documented
    as no interaction."""
    assert matrix._number(3e-5) not in ("0", "-0") and float(matrix._number(3e-5)) == 3e-5
    assert matrix._number(-3e-5) not in ("0", "-0") and float(matrix._number(-3e-5)) == -3e-5
    # nothing else moves
    assert matrix._number(-3.46441) == "-3.4644" and matrix._number(0.0412) == "0.0412"
    assert matrix._number(0) == "0" and matrix._number(None) == "NA" and matrix._number(2.0) == "2"


def test_the_package_says_to_match_rates_to_a_matrix_by_name():
    """#210: with several units, each matrix holds its unit's organisms in its own order beside ONE rates
    file in another order, and a positional join gave a plausible, wrong simulation."""
    readme = matrix.glv_payload(_net(PAIR), RATES)["readme"]
    assert "NEVER BY POSITION" in readme and "match(rownames(A), rates$organism)" in readme
