"""One search at the shipped defaults, end to end (#142 item 11).

Every other page, command-line, report, export and threshold test asks for `derivation=replicate`,
because the double those tests share measures two points per set, which is all the specified comparison
needs and far too few to fit a row from a time course. So the derivation that actually produces the daily
artifact and every default user's file was covered end to end nowhere, which is why #142 item 5 survived
twelve commits: `meta.statistics` claimed Welch's t-test over replicate sets for networks derived by a
form that compares no sets.

This file is the missing coverage. The double serves simulated gLV time courses, `run_query` runs at the
shipped defaults with nothing overridden, and the test asserts both halves: the search gives arcs, and
what the network says about itself describes the derivation that made them.
"""
import math

import pytest

from grownet.gui import DEFAULTS, run_query

A = "Faecalibacterium prausnitzii A2-165"
B = "Blautia hydrogenotrophica DSM 10507"
TAXA = {A: 853, B: 53443}
# B facilitates A and A does not affect B, the same shape the other double has, with a self-limitation
# each so both rows are identifiable
RATES = {A: 0.4, B: 0.3}
EFFECTS = {(A, A): -4.0e-10, (A, B): 2.0e-10, (B, A): 0.0, (B, B): -3.0e-10}
START = {A: 1.0e7, B: 5.0e8}


def _simulate(members, inoculum, t_end=10.0, step=0.01, keep=20):
    """The community integrated with small Euler steps, kept every twentieth point: the measured curves a
    fit should recover the coefficients from."""
    x = dict(inoculum)
    times, series = [0.0], [dict(x)]
    for k in range(1, int(t_end / step) + 1):
        grown = {m: x[m] * (RATES[m] + sum(EFFECTS[(m, o)] * x[o] for o in members)) for m in members}
        x = {m: max(1e-12, x[m] + step * grown[m]) for m in members}
        if k % keep == 0:
            times.append(k * step)
            series.append(dict(x))
    return times, series


def _experiment(name, members):
    return {
        "id": "E_" + name, "name": name, "cultivationMode": "batch", "description": name,
        "compartments": [{"mediumName": "Wilkins-Chalgren Anaerobe Broth"}],
        "communityStrains": [{"name": m, "NCBId": TAXA[m]} for m in members],
        "bioreplicates": [{"id": f"{name}/{i}", "name": f"{name}_{i}"} for i in (0, 1, 2)],
    }


DESIGN = {"mono A": [A], "mono B": [B], "co": [A, B]}
EXPERIMENTS = [_experiment(name, members) for name, members in DESIGN.items()]
# one simulation per experiment and replicate, the replicates differing only in their inoculum
SERIES = {}
for _name, _members in DESIGN.items():
    for _i in (0, 1, 2):
        _factor = (0.9, 1.0, 1.1)[_i]
        SERIES[(_name, _i)] = _simulate(_members, {m: START[m] * _factor for m in _members})


class TimeCourseClient:
    """One study of three experiments whose bioreplicates carry measured time courses."""

    study_id = "SMGDB00000001"

    def get_study(self, study_id):
        return {"id": study_id, "name": "simulated study", "url": "http://example/study",
                "uploadedAt": "2025-06-26T13:03:03+00:00", "publishedAt": "2025-06-29T10:25:52+00:00",
                "experiments": [{"id": e["id"]} for e in EXPERIMENTS]}

    def study_experiments(self, study_id):
        return EXPERIMENTS

    def get_experiment(self, experiment_id):
        return next(e for e in EXPERIMENTS if e["id"] == experiment_id)

    def get_bioreplicate(self, bioreplicate_id):
        name, _, index = str(bioreplicate_id).partition("/")
        return {"id": bioreplicate_id, "name": f"{name}_{index}", "isAverage": False,
                "measurementTimeUnits": "h",
                "measurementContexts": [
                    {"id": f"{name}/{index}/{m}", "techniqueType": "qpcr", "techniqueUnits": "Cells/mL",
                     "subject": {"type": "strain", "name": m}}
                    for m in DESIGN[name]]}

    def get_measurement_series(self, context_id):
        name, index, species = str(context_id).split("/")
        times, series = SERIES[(name, int(index))]
        return [(t, row[species], None) for t, row in zip(times, series, strict=True)]

    def search(self, strain_ncbi_ids=None, metabolite_chebi_ids=None):
        return {"studies": [self.study_id]}


def _default_query():
    """Nothing overridden: whatever the page would do for a reader who changes no setting."""
    return run_query(TimeCourseClient(), [A, B], {})


def _arc(result, source, target):
    """The arc from `source` to `target`, looked up by the names their nodes carry."""
    net = result["network"]
    named = {nid: node.name for nid, node in net.nodes.items()}
    return next(e for e in net.edges if named.get(e.source) == source and named.get(e.target) == target)


def test_the_shipped_default_derives_arcs_from_a_time_course():
    result = _default_query()
    assert result["settings"]["derivation"] == DEFAULTS["derivation"] == "integrated"
    assert result["errors"] == [] and result["unresolved"] == []
    assert result["network"].edges, "the shipped default derived nothing from a time course"
    # B facilitates A, which is the only non-zero off-diagonal in the simulation
    facilitation = _arc(result, B, A)
    assert facilitation.effect == "facilitation" and facilitation.coefficient > 0
    assert facilitation.coefficient_unit.startswith("1/(h x ")
    # the identity the arc rests on, which is what makes it comparable with a ratio arc
    assert facilitation.strength is not None


def test_what_the_network_says_about_itself_describes_the_derivation_that_made_it():
    """#142 item 5, end to end: `meta.statistics` and `meta.provisional` used to be module constants
    copied into every network, so a file derived by the integrated form said it had run Welch's
    two-sided t-test on per-replicate log2 values and compared replicate sets."""
    meta = _default_query()["network"].meta
    said = meta["statistics"]["test"]
    assert "Welch" not in said
    assert "fitted log2 strength" in said and "monoculture stage" in said
    assert "Satterthwaite" in said
    assert "Welch" not in meta["provisional"]
    assert "generalized Lotka-Volterra" in meta["provisional"]
    # and the rest of meta.statistics is still the machinery that ran: the correction and the count
    assert "Benjamini-Hochberg" in meta["statistics"]["correction"]
    assert meta["statistics"]["tests"] >= 0


def test_the_report_the_page_and_the_export_all_carry_the_derivations_own_words():
    """The claim travelled into the report, the page and GraphML, so each is checked where a reader meets
    it rather than only in `meta`."""
    from grownet.export import to_graphml
    from grownet.gui import render_result
    from grownet.report import report_text
    result = _default_query()

    text = report_text(result)
    assert "Welch" not in text
    assert "fitted log2 strength" in text

    page = render_result("tok", result)
    assert "Welch" not in page

    graphml = to_graphml(result["network"])
    assert "Welch" not in graphml


def test_the_statistics_a_default_arc_carries_are_the_two_component_ones():
    """#142 item 2 end to end: an arc's `se` carries the monoculture stage, and says how much of it does."""
    result = _default_query()
    arc = _arc(result, B, A)
    assert arc.se is not None and arc.sd is not None
    assert arc.se_replicates is not None and arc.se_rate_stage is not None
    assert arc.rate_stage_method.startswith("bootstrap of 3 monoculture replicate(s)")
    assert arc.rate_stage_n == 3
    # `se` is rounded to four decimals on the record, so the relation holds to half of the last digit
    assert arc.se == pytest.approx(math.sqrt(arc.se_replicates ** 2 + arc.se_rate_stage ** 2), abs=5e-5)


def test_the_package_prose_states_the_formula_the_derivation_actually_fitted():
    """#142 item 6: the gLV package's README.txt and the payload's `caveats.coefficients` stated the
    comparison's formula, `(r_with - r_without) / x_j` over a rate window, for every package including
    one derived by the integrated form, which fits the row from the time course and never takes that
    difference. Both now follow the derivation, and `caveats.derivation` names it."""
    import zipfile

    from grownet import matrix
    result = _default_query()
    net, rates = result["network"], result.get("rates") or {}
    assert matrix.derivation_of(net) == "integrated"

    payload = matrix.glv_payload(net, rates)
    assert payload["caveats"]["derivation"] == "integrated"
    assert "(r_with - r_without)" not in payload["caveats"]["coefficients"]
    assert "integral(x_j dt)" in payload["caveats"]["coefficients"]

    with zipfile.ZipFile(io_bytes(matrix.glv_package(net, rates))) as archive:
        readme = archive.read("README.txt").decode("utf-8")
    assert "(r_with - r_without)" not in readme
    assert "fitted from the whole measured time course" in readme

    # and the comparison's own package still states the comparison's formula
    other = run_query(TimeCourseClient(), [A, B], {"derivation": "replicate", "metric": "growth_rate"})
    assert matrix.derivation_of(other["network"]) == "replicate"
    said = matrix.glv_payload(other["network"], other.get("rates") or {})["caveats"]["coefficients"]
    assert "(r_with - r_without)" in said


def io_bytes(data: bytes):
    import io
    return io.BytesIO(data)


def test_the_zip_and_the_payload_carry_the_same_numbers_to_four_significant_digits():
    """#142 item 15, Craig's agent on #135: that PR exists to establish that the two routes carry the same
    numbers, and each was tested against hand arithmetic on its own fixture rather than against the other.
    They agree to four significant digits, because `coefficient_csv` is `.4g` and the payload carries the
    raw float, so a reader who diffs them finds a difference in the fifth digit and should not have to
    wonder which is wrong."""
    import csv
    import io
    import zipfile

    from grownet import matrix
    result = _default_query()
    net, rates = result["network"], result.get("rates") or {}
    payload = matrix.glv_payload(net, rates)

    with zipfile.ZipFile(io_bytes(matrix.glv_package(net, rates))) as archive:
        name = next(n for n in archive.namelist() if n.startswith("interaction_matrix"))
        rows = list(csv.reader(io.StringIO(archive.read(name).decode("utf-8"))))

    header, body = rows[0][1:], rows[1:]
    from_zip = {(row[0], header[j]): float(value)
                for row in body for j, value in enumerate(row[1:]) if value not in ("", "0")}
    block = payload["matrices"][0]
    names = block["organisms"]
    from_payload = {(names[i], names[j]): block["interactions"][i][j]
                    for i in range(len(names)) for j in range(len(names))}
    assert from_zip, "the package held no non-zero cell to compare"
    for key, value in from_zip.items():
        assert key in from_payload, key
        # four significant digits is what the CSV carries, and no more is claimed of the agreement
        assert value == pytest.approx(from_payload[key], rel=1e-4), key
