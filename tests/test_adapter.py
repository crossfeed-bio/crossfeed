"""mGrowthDB experiments to replicate curves (a fake client, no live calls)."""
import pytest

from crossfeed.adapter import replicate_sets, replicates_for_experiment

A = "Faecalibacterium prausnitzii A2-165"
B = "Blautia hydrogenotrophica DSM 10507"
SERIES = [(0.0, 1.0e6, None), (2.0, 4.0e6, None), (4.0, 9.0e6, None)]


def _context(cid, species, unit="Cells/mL", technique="qpcr"):
    return {"id": cid, "techniqueType": technique, "techniqueUnits": unit,
            "subject": {"type": "strain", "name": species}}


def _bioreplicate(bid, name, contexts, is_average=False, time_unit="h"):
    return {"id": bid, "name": name, "isAverage": is_average, "measurementTimeUnits": time_unit,
            "measurementContexts": contexts}


class FakeClient:
    """Bioreplicates and series by id; a missing id raises, as the API does."""

    def __init__(self, bioreplicates, series=None):
        self.bioreplicates = bioreplicates
        self.series = series or {}
        self.series_calls = []

    def get_bioreplicate(self, bid):
        if bid not in self.bioreplicates:
            raise RuntimeError(f"mGrowthDB returned HTTP 404 for bioreplicate {bid}")
        return self.bioreplicates[bid]

    def get_measurement_series(self, context_id):
        self.series_calls.append(context_id)
        if context_id not in self.series:
            raise RuntimeError(f"mGrowthDB returned HTTP 404 for measurement-context {context_id}")
        return self.series[context_id]


def _experiment(name="co-culture", stubs=((1, "r1"), (2, "r2"))):
    return {"id": "E1", "name": name, "bioreplicates": [{"id": i, "name": n} for i, n in stubs]}


def _client_with_pair():
    bioreplicates = {
        1: _bioreplicate(1, "r1", [_context(11, A), _context(12, B)]),
        2: _bioreplicate(2, "r2", [_context(21, A), _context(22, B)]),
    }
    series = {cid: SERIES for cid in (11, 12, 21, 22)}
    return FakeClient(bioreplicates, series)


def test_each_bioreplicate_becomes_a_replicate_with_a_curve_per_strain():
    replicates, skipped = replicates_for_experiment(_client_with_pair(), _experiment())
    assert [r.name for r in replicates] == ["r1", "r2"]
    assert skipped == []
    curve = replicates[0].curve(A)
    assert curve.times == (0.0, 2.0, 4.0)
    assert curve.values == (1.0e6, 4.0e6, 9.0e6)
    assert curve.time_unit == "h" and curve.abundance_unit == "Cells/mL"


def test_average_bioreplicate_is_left_out_with_a_reason():
    client = _client_with_pair()
    client.bioreplicates[3] = _bioreplicate(3, "Average(r1,r2)", [_context(31, A)], is_average=True)
    replicates, skipped = replicates_for_experiment(client, _experiment(stubs=((1, "r1"), (3, "Average(r1,r2)"))))
    assert [r.name for r in replicates] == ["r1"]
    assert skipped == [("co-culture: Average(r1,r2)", "average of the replicates, not an independent replicate")]
    assert 31 not in client.series_calls          # its series is never fetched


def test_unit_falls_back_to_the_technique_when_none_is_reported():
    client = _client_with_pair()
    client.bioreplicates[1]["measurementContexts"] = [_context(11, A, unit="")]
    replicates, _ = replicates_for_experiment(client, _experiment(stubs=((1, "r1"),)))
    assert replicates[0].curve(A).abundance_unit == "qpcr"


def test_a_series_too_short_or_missing_is_reported_not_guessed():
    client = _client_with_pair()
    client.series[11] = [(0.0, 1.0e6, None)]      # one point
    del client.series[12]                          # missing entirely
    replicates, skipped = replicates_for_experiment(client, _experiment(stubs=((1, "r1"),)))
    reasons = dict(skipped)
    assert "1 measured time point(s)" in reasons[f"co-culture: r1, {A}"]
    assert "could not read its series" in reasons[f"co-culture: r1, {B}"]
    assert replicates == [] and "no usable per-strain series" in reasons["co-culture: r1"]


def test_an_unreadable_bioreplicate_does_not_lose_the_others():
    client = _client_with_pair()
    replicates, skipped = replicates_for_experiment(client, _experiment(stubs=((1, "r1"), (9, "gone"))))
    assert [r.name for r in replicates] == ["r1"]
    assert "could not read it" in dict(skipped)["co-culture: gone"]


def test_community_level_contexts_are_ignored():
    client = _client_with_pair()
    client.bioreplicates[1]["measurementContexts"].append(
        {"id": 19, "techniqueUnits": "OD600", "subject": {"type": "bioreplicate", "name": "Community OD"}})
    replicates, _ = replicates_for_experiment(client, _experiment(stubs=((1, "r1"),)))
    assert sorted(replicates[0].species) == sorted([A, B])
    assert 19 not in client.series_calls


def test_replicate_sets_sorts_monocultures_and_co_cultures():
    client = _client_with_pair()
    client.bioreplicates[4] = _bioreplicate(4, "a1", [_context(41, A)])
    client.bioreplicates[5] = _bioreplicate(5, "b1", [_context(51, B)])
    client.series.update({41: SERIES, 51: SERIES})
    experiments = [_experiment("co", ((1, "r1"),)), _experiment("mono A", ((4, "a1"),)),
                   _experiment("mono B", ((5, "b1"),))]
    mono_a, mono_b, co, skipped = replicate_sets(client, experiments, A, B)
    assert [r.name for r in mono_a] == ["a1"]
    assert [r.name for r in mono_b] == ["b1"]
    assert [r.name for r in co] == ["r1"]
    assert skipped == []


def test_a_larger_community_is_reported_not_forced():
    client = _client_with_pair()
    third = "Roseburia intestinalis L1-82"
    client.bioreplicates[1]["measurementContexts"].append(_context(13, third))
    client.series[13] = SERIES
    mono_a, mono_b, co, skipped = replicate_sets(client, [_experiment("trio", ((1, "r1"),))], A, B)
    assert co == [] and mono_a == [] and mono_b == []
    assert "holds" in dict(skipped)["trio: r1"]


@pytest.mark.parametrize("bad_series", [[(0.0, 1.0, None), (0.0, 2.0, None)], [(1.0, 1.0, None), (0.5, 2.0, None)]])
def test_unusable_time_points_are_reported(bad_series):
    client = _client_with_pair()
    client.series[11] = bad_series
    _, skipped = replicates_for_experiment(client, _experiment(stubs=((1, "r1"),)))
    assert any("increasing" in reason for _, reason in skipped)


# ---- alternatives for a flagged curve (#39) --------------------------------------------------------

SPIKY = [(0.0, 1.0e6, None), (2.0, 1.0e11, None), (4.0, 2.0e6, None), (6.0, 4.0e6, None), (8.0, 8.0e6, None)]
CLEAN = [(0.0, 1.0e6, None), (2.0, 2.0e6, None), (4.0, 4.0e6, None), (6.0, 8.0e6, None), (8.0, 9.0e6, None)]


def test_a_spiked_monoculture_curve_names_the_clean_community_trace():
    community_fc = {"id": 91, "techniqueType": "fc", "techniqueUnits": "Cells/mL",
                    "subject": {"type": "bioreplicate", "name": "m1"}}
    metabolite = {"id": 92, "techniqueType": "metabolite", "techniqueUnits": "mM",
                  "subject": {"type": "metabolite", "name": "formic acid"}}
    client = FakeClient({1: _bioreplicate(1, "m1", [_context(11, B), community_fc, metabolite])},
                        {11: SPIKY, 91: CLEAN, 92: CLEAN})
    replicates, _ = replicates_for_experiment(client, _experiment("BH", ((1, "m1"),)))
    note = replicates[0].notes[B]
    assert "community fc clean" in note and "not substituted" in note
    assert "metabolite" not in note          # a metabolite trace is not a measurement of the strain


def test_in_a_co_culture_the_community_trace_is_not_an_alternative():
    community_fc = {"id": 91, "techniqueType": "fc", "subject": {"type": "bioreplicate", "name": "r1"}}
    client = FakeClient({1: _bioreplicate(1, "r1", [_context(11, A), _context(12, B), community_fc])},
                        {11: CLEAN, 12: SPIKY, 91: CLEAN})
    replicates, _ = replicates_for_experiment(client, _experiment("co", ((1, "r1"),)))
    note = replicates[0].notes[B]
    assert "community" in note and "measure all members together" in note
    assert A not in replicates[0].notes      # A's clean curve gets no note


def test_alternatives_are_only_fetched_for_a_flagged_curve():
    community_fc = {"id": 91, "techniqueType": "fc", "subject": {"type": "bioreplicate", "name": "m1"}}
    client = FakeClient({1: _bioreplicate(1, "m1", [_context(11, B), community_fc])}, {11: CLEAN, 91: CLEAN})
    replicates, _ = replicates_for_experiment(client, _experiment("BH", ((1, "m1"),)))
    assert replicates[0].notes == {} and 91 not in client.series_calls



def test_two_contexts_for_one_strain_in_a_replicate_are_reported_not_fatal():
    # SMGDB00000002: mucin experiments carry one context per compartment for the same strain, with the same
    # technique and label, and the API does not say which compartment each belongs to
    client = _client_with_pair()
    client.bioreplicates[1]["measurementContexts"].append(_context(19, A))
    client.series[19] = SERIES
    replicates, skipped = replicates_for_experiment(client, _experiment(stubs=((1, "r1"), (2, "r2"))))
    assert [r.species for r in replicates] == [(B,), (A, B)]      # r1 keeps B, r2 is untouched
    assert "2 measurement contexts for this strain" in dict(skipped)[f"co-culture: r1, {A}"]
