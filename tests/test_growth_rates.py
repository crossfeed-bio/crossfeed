"""The absolute monoculture growth rates reported beside a network (#108).

Karoline, 2026-10-03: a reported rate is the "Maximum specific growth rate in monoculture (easylinear, as
mGrowthDB reports), median across replicates and studies, with the per-study values kept beside it".

Every expected number here is hand computed. A culture that doubles every 2 h has the specific growth rate
ln(2) / 2 = 0.34657 per hour, and easylinear fits a straight line to the natural log of abundance, so a
clean exponential curve returns exactly that.
"""
import math

import pytest

from grownet.derive import growth_rates, merge_rates, monoculture_rates

A = "Faecalibacterium prausnitzii A2-165"
B = "Blautia hydrogenotrophica DSM 10507"


def _exponential(doubling: float, points: int = 8, start: float = 1.0e6):
    """A curve doubling every `doubling` hours: (time, value, None) per hour."""
    return [(float(t), start * 2 ** (t / doubling), None) for t in range(points)]


def _context(cid, species):
    return {"id": cid, "techniqueType": "qpcr", "techniqueUnits": "Cells/mL",
            "subject": {"type": "strain", "name": species}}


def _mono(exp_id, name, replicates, mode="batch"):
    """A monoculture experiment with one bioreplicate per entry of `replicates` ((id, name) pairs)."""
    return {"id": exp_id, "name": f"{name} alone", "cultivationMode": mode,
            "communityStrains": [{"name": name}],
            "bioreplicates": [{"id": bid, "name": rname} for bid, rname in replicates]}


def _co(exp_id, a, b, replicates):
    return {"id": exp_id, "name": f"{a} with {b}", "cultivationMode": "batch",
            "communityStrains": [{"name": a}, {"name": b}],
            "bioreplicates": [{"id": bid, "name": rname} for bid, rname in replicates]}


class FakeClient:
    """Bioreplicates and series by id, like the API; studies and experiments for `growth_rates`."""

    def __init__(self, bioreplicates, series, studies=None, experiments=None):
        self.bioreplicates, self.series = bioreplicates, series
        self.studies, self.experiments = studies or {}, experiments or {}

    def get_bioreplicate(self, bid):
        return self.bioreplicates[bid]

    def get_measurement_series(self, context_id):
        return self.series[context_id]

    def get_study(self, study_id):
        return self.studies[study_id]

    def get_experiment(self, experiment_id):
        return self.experiments[experiment_id]


def _client(curves, time_unit="h"):
    """curves: {(bioreplicate id, species): series}. One context per (replicate, species)."""
    bioreplicates, series = {}, {}
    for i, ((bid, species), curve) in enumerate(sorted(curves.items(), key=lambda kv: (kv[0][0], kv[0][1]))):
        cid = 1000 + i
        series[cid] = curve
        rep = bioreplicates.setdefault(bid, {"id": bid, "name": f"r{bid}", "isAverage": False,
                                             "measurementTimeUnits": time_unit, "measurementContexts": []})
        rep["measurementContexts"].append(_context(cid, species))
    return FakeClient(bioreplicates, series)


DOUBLES_EVERY_2H = math.log(2) / 2          # 0.34657..., the rate of every curve built with doubling=2


def test_a_monoculture_rate_is_the_maximum_specific_growth_rate_of_that_organism():
    client = _client({(1, A): _exponential(2.0)})
    found, skipped = monoculture_rates(client, [_mono("E1", A, [(1, "r1")])])
    # keyed by node id: no taxon id in these records, so the strain is identified by genus and species
    assert list(found) == ["faecalibacterium prausnitzii"]
    (entry,) = found.values()
    assert entry["name"] == A and entry["unit"] == "1/h"
    assert entry["values"] == pytest.approx([DOUBLES_EVERY_2H], rel=1e-9)
    assert skipped == []


def test_a_co_culture_gives_no_rate_because_that_is_growth_with_a_partner():
    client = _client({(1, A): _exponential(2.0), (2, A): _exponential(2.0), (2, B): _exponential(3.0)})
    exps = [_mono("E1", A, [(1, "r1")]), _co("E2", A, B, [(2, "r2")])]
    found, _ = monoculture_rates(client, exps)
    assert [e["name"] for e in found.values()] == [A]  # B was only ever in the co-culture, so it has no rate


def test_a_chemostat_monoculture_gives_no_rate_and_says_why():
    client = _client({(1, A): _exponential(2.0)})
    found, skipped = monoculture_rates(client, [_mono("E1", A, [(1, "r1")], mode="chemostat")])
    assert found == {}
    assert any("chemostat" in reason for _, reason in skipped)


def test_a_curve_too_short_for_a_rate_is_reported_not_replaced_by_another_number():
    client = _client({(1, A): _exponential(2.0, points=4)})   # easylinear with a window of 5 needs 6 points
    found, skipped = monoculture_rates(client, [_mono("E1", A, [(1, "r1")])])
    assert found == {}
    assert [label for label, _ in skipped] == [f"{A} monoculture [{A} alone], replicate r1"]
    assert "no growth rate" in skipped[0][1]


def test_only_the_organisms_asked_for_are_read():
    client = _client({(1, A): _exponential(2.0), (2, B): _exponential(2.0)})
    exps = [_mono("E1", A, [(1, "r1")]), _mono("E2", B, [(2, "r2")])]
    found, _ = monoculture_rates(client, exps, wanted={"blautia hydrogenotrophica"})
    assert [e["name"] for e in found.values()] == [B]


def test_the_rate_is_the_median_over_replicates_and_studies_with_each_study_kept_beside_it():
    # study 1: two replicates doubling every 2 h and every 4 h; study 2: one doubling every 1 h.
    # pooled rates are ln2/4 = 0.1733, ln2/2 = 0.3466 and ln2 = 0.6931, so the median is ln2/2
    one = {"ncbi:1": {"name": A, "unit": "1/h", "values": [math.log(2) / 2, math.log(2) / 4],
                      "replicates": ["r1", "r2"]}}
    two = {"ncbi:1": {"name": A, "unit": "1/h", "values": [math.log(2)], "replicates": ["r1"]}}
    merged = merge_rates([("S1", one), ("S2", two)])
    rate = merged["ncbi:1"]
    assert rate["rate"] == pytest.approx(math.log(2) / 2)
    assert rate["n"] == 3 and rate["studies"] == ["S1", "S2"]
    # each study's own median beside it: S1 is the mean of its two values, S2 is its single value
    assert rate["per_study"]["S1"] == pytest.approx((math.log(2) / 2 + math.log(2) / 4) / 2)
    assert rate["per_study"]["S2"] == pytest.approx(math.log(2))


def test_rates_in_another_time_unit_are_named_not_converted():
    hours = {"ncbi:1": {"name": A, "unit": "1/h", "values": [0.4], "replicates": ["r1"]}}
    minutes = {"ncbi:1": {"name": A, "unit": "1/min", "values": [0.007], "replicates": ["r1"]}}
    rate = merge_rates([("S1", hours), ("S2", minutes)])["ncbi:1"]
    assert rate["rate"] == 0.4 and rate["unit"] == "1/h" and rate["studies"] == ["S1"]
    assert rate["other_units"] == ["S2 (1/min)"]


def test_rates_are_collected_from_every_study_the_search_read():
    client = _client({(1, A): _exponential(2.0), (2, B): _exponential(2.0)})
    client.experiments = {"E1": _mono("E1", A, [(1, "r1")]), "E2": _mono("E2", B, [(2, "r2")])}
    client.studies = {"S1": {"id": "S1", "experiments": [{"id": "E1"}]},
                      "S2": {"id": "S2", "experiments": [{"id": "E2"}]}}
    found, skipped = growth_rates(client, ["S1", "S2"])
    assert sorted(e["name"] for e in found.values()) == sorted([A, B])
    assert all(e["rate"] == pytest.approx(DOUBLES_EVERY_2H) for e in found.values())
    assert skipped == []
