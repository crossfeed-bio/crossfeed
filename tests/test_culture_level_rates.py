"""Rates from culture-level counts of a monoculture (#140) and no pooling across starting densities (#81 b).

Karoline: "yes to #140 with option 1" (2026-10-07), "Counts only" (2026-10-12), and on #81 "I'd also pick
b)" (2026-10-12): a monoculture measured only as a whole culture gives its rate and lag from a plate count
or flow cytometry, never from optical density and never a capacity; and a rate is not pooled across
measured starting densities more than 10 times apart.
"""
import math

from grownet import derive
from grownet.adapter import culture_trace_replicates
from grownet.rates import RateUnavailable, baranyi_fit

STRAIN = "Escherichia coli LF82"


def _logistic(start, rate=0.5, top=1e9, n=40):
    """A logistic curve sampled every hour: a rate, a lag-free start and a plateau."""
    return [(float(t), top / (1 + (top / start - 1) * math.exp(-rate * t)), None) for t in range(n)]


class CultureClient:
    """Monoculture experiments whose bioreplicates carry only culture-level contexts."""

    def __init__(self, techniques_by_rep, starts=None):
        self.techniques_by_rep, self.starts = techniques_by_rep, starts or {}

    def get_bioreplicate(self, rid):
        return {"id": rid, "name": rid, "isAverage": False, "measurementTimeUnits": "h",
                "measurementContexts": [
                    {"id": f"{rid}/{t}/{i}", "techniqueType": t,
                     "techniqueUnits": {"plates": "CFUs/mL", "fc": "Cells/mL"}.get(t, ""),
                     "subject": {"type": "bioreplicate"}}
                    for i, t in enumerate(self.techniques_by_rep[rid])]}

    def get_measurement_series(self, cid):
        rid, technique, _ = cid.split("/")
        return _logistic(self.starts.get(rid, 1e5)) if technique != "ph" else [(t, 7.0, None) for t in range(16)]


def _exp(reps, name="mono"):
    return {"id": name, "name": name, "cultivationMode": "batch", "communityStrains": [{"name": STRAIN, "NCBId": 1}],
            "bioreplicates": [{"id": r, "name": r} for r in reps]}


def test_a_count_is_taken_and_optical_density_never():
    client = CultureClient({"r1": ["od", "fc", "ph"], "r2": ["od", "ph"], "r3": ["plates", "fc"],
                            "r4": ["fc", "fc"]})
    reps, skipped = culture_trace_replicates(client, _exp(["r1", "r2", "r3", "r4"]), STRAIN)
    assert [(r.name, r.curve(STRAIN).technique) for r in reps] == \
        [("r1", "culture-level fc"), ("r3", "culture-level plates")]
    reasons = dict(skipped)
    assert "no single culture-level count" in reasons["mono: r2"], "OD alone gives nothing"
    assert "no single culture-level count" in reasons["mono: r4"], "two counts and nothing says which"


def test_the_rate_and_lag_come_from_the_count_and_the_capacity_never(monkeypatch):
    client = CultureClient({"r1": ["fc"], "r2": ["fc"], "r3": ["fc"]})
    monkeypatch.setattr(derive, "replicates_for_experiment", lambda *a, **k: ([], [("mono: r1", "no usable")]))
    found, _ = derive.monoculture_rates(client, [_exp(["r1", "r2", "r3"])], identities={})
    (entry,) = found.values()
    assert len(entry["values"]) == 3 and abs(entry["values"][0] - 0.5) < 0.1
    assert entry["sources"] == {"culture-level fc": 3}
    assert entry["capacity_by_medium"] == {}, "a plateau is never read from a culture-level trace"
    # the curve DOES reach a plateau, so the empty capacity is the guard and not the data (found in review:
    # a 16-point curve never reached stationary, so deleting the guard left this green)
    from grownet.growth import GrowthCurve, reached_stationary
    points = _logistic(1e5)
    curve = GrowthCurve(STRAIN, [t for t, _, _ in points], [v for _, v, _ in points], "h", "Cells/mL")
    assert reached_stationary(curve, curve.times[-1]) is True
    merged = derive.merge_rates([("S9", found)])
    (rate,) = merged.values()
    assert rate["rate_sources"] == {"culture-level fc": 3} and rate["capacity"] is None


def test_a_rate_is_not_pooled_across_starts_more_than_ten_times_apart(monkeypatch):
    """SMGDB00000014's Comamonas monocultures start from 1e4 to 1.01e6 CFU/mL, 101 times apart, live."""
    monkeypatch.setattr(derive, "replicates_for_experiment", lambda *a, **k: ([], []))
    wide = CultureClient({"a": ["plates"], "b": ["plates"]}, starts={"a": 1e4, "b": 1.01e6})
    found, skipped = derive.monoculture_rates(wide, [_exp(["a", "b"])], identities={})
    assert any("101 times apart" in why for _, why in skipped), skipped
    # no rate, and the reason travels with the organism to where its rate would be (round 14 of the
    # review: the page said no monoculture was read, or its curves gave none, both false)
    ((nid, entry),) = found.items()
    assert entry["values"] == [] and "101 times apart" in entry["refused"]
    merged = derive.merge_rates([("S14", found)])
    name, why = merged.no_rate[nid]
    assert nid not in merged and why.startswith("its monocultures' growth rates were left out: S14:")
    # every study's reason is kept, not the last one read (round 15 of the review)
    both = derive.merge_rates([("S14", found), ("S15", found)]).no_rate[nid][1]
    assert "S14: they started" in both and "S15: they started" in both
    # refused in one study and measured in another: a rate, and no reason for having none (round 15)
    measured = {nid: {**entry, "values": [0.5, 0.6], "refused": None, "sources": {"per-strain": 2}}}
    mixed = derive.merge_rates([("S14", found), ("S15", measured)])
    assert nid in mixed and nid not in mixed.no_rate
    from grownet import gui, matrix
    from grownet.mgrowthdb import records_to_network
    net = records_to_network([{"source": nid, "target": "x", "source_name": "Comamonas testosteroni",
                               "target_name": "X", "source_identity": "ncbi", "effect": "facilitation",
                               "strength": 1.0, "study_id": "S14"}])
    rows = matrix.for_nodes(net, merged)
    net.meta["growth_rates"] = matrix.rate_meta(net, rows, "m")
    hint = gui._without_a_rate({"network": net})
    assert "No growth rate for Comamonas testosteroni: its monocultures&#x27; growth rates were left out" in hint, hint
    assert "101 times apart" in hint
    # and a genus of such strains says whose they were (round 15: keyed by strain id, it never reached the
    # genus node, and the page gave the general reason, both causes false)
    assert name == "Escherichia coli LF82"
    genus = records_to_network([{"source": "escherichia", "target": "x", "source_name": "Escherichia",
                                 "target_name": "X", "source_identity": "genus", "effect": "facilitation",
                                 "strength": 1.0, "study_id": "S14"}])
    other = derive.OrganismRates(merged)
    other.no_rate.update(merged.no_rate)
    other.no_rate["ncbi:999"] = ("Klebsiella oxytoca", "its monocultures' growth rates were left out: S9: (#81)")
    rows = matrix.for_nodes(genus, other)
    # only this genus's strains: a refused strain of another genus is not named here (round 16)
    assert rows.no_rate == {"Escherichia": f"{name}: {why}"}, rows.no_rate
    # a strain renamed into another genus (#24) gives its reason to the genus it is shown in now (round 16)
    renamed = derive.OrganismRates()
    renamed.no_rate["ncbi:562"] = (name, why)
    shigella = records_to_network([{"source": "shigella", "target": "x", "source_name": "Shigella",
                                    "target_name": "X", "source_identity": "genus", "effect": "facilitation",
                                    "strength": 1.0, "study_id": "S14"}])
    current = {562: "Shigella coli LF82"}
    assert matrix.for_nodes(shigella, renamed, current).no_rate == {"Shigella": f"Shigella coli LF82: {why}"}
    assert matrix.for_nodes(genus, renamed, current).no_rate == {}, "not on the genus it was read under"
    # two refused strains of one genus, one of them renamed into it: both named, by their current names
    renamed.no_rate["ncbi:563"] = ("Shigella flexneri 2a", "its monocultures' growth rates were left out: S9: x")
    assert matrix.for_nodes(shigella, renamed, current).no_rate == {
        "Shigella": f"Shigella coli LF82: {why}; Shigella flexneri 2a: its monocultures' growth rates were left "
                    "out: S9: x"}
    # a strain node with no rate is not given a refused sibling's reason (the guard on genus nodes)
    sibling = records_to_network([{"source": "ncbi:83333", "target": "x", "source_name": "Shigella coli K12",
                                   "target_name": "X", "source_identity": "ncbi", "effect": "facilitation",
                                   "strength": 1.0, "study_id": "S14"}])
    assert matrix.for_nodes(sibling, renamed, current).no_rate == {}
    near = CultureClient({"a": ["plates"], "b": ["plates"]}, starts={"a": 1e5, "b": 9e5})
    found, skipped = derive.monoculture_rates(near, [_exp(["a", "b"])], identities={})
    assert len(next(iter(found.values()))["values"]) == 2, "nine times apart is still one set"


def test_a_baranyi_start_that_runs_off_is_a_rejected_fit_not_a_crash():
    """First met on SMGDB00000025's optical densities: math.exp raised OverflowError on a start's log-rate."""
    import grownet.rates as rates
    original = rates._fit_once
    try:
        rates._fit_once = lambda xs, ys, start: ([start[0], 1e6, start[2], start[3]], 0.0)
        times = [float(t) for t in range(12)]
        values = [math.exp(0.3 * t) for t in times]
        import pytest
        with pytest.raises(RateUnavailable):
            baranyi_fit(times, values)
    finally:
        rates._fit_once = original


def test_a_culture_level_rate_says_why_it_has_no_capacity(monkeypatch):
    """Round 2 of the review: nothing a consumer reads said a rate came from a culture-level count; the
    existing capacity_source carries it, with no new field in grownet.glv/v1."""
    from grownet import matrix
    client = CultureClient({"r1": ["fc"], "r2": ["fc"]})
    monkeypatch.setattr(derive, "replicates_for_experiment", lambda *a, **k: ([], []))
    found, _ = derive.monoculture_rates(client, [_exp(["r1", "r2"])], identities={})
    (rate,) = derive.merge_rates([("S9", found)]).values()
    assert rate["capacity_source"] == ("none: the rate is from a culture-level fc count (2 replicate(s)), which "
                                       "never gives a capacity"), rate["capacity_source"]
    assert "never gives a capacity" in matrix.rates_csv({"x": rate})


def test_the_payload_counts_capacity_curves_not_fitted_rows():
    """Round 1 fixed carrying_capacity_curves to prefer the curve count, and nothing failed without it."""
    from test_payload_v1 import PAIR, RATES, _net

    from grownet import matrix
    rates = {k: {**v, "capacity_curves": 4, "capacity_n": 1} for k, v in RATES.items()}
    detail = matrix.glv_payload(_net(PAIR), rates)["growth_rate_detail"]
    assert {d["carrying_capacity_curves"] for d in detail} == {4}


def test_a_rate_partly_from_per_strain_curves_does_not_blame_the_count_for_its_missing_capacity(monkeypatch):
    """Round 3 of the review: a rate from 3 per-strain replicates and 1 culture-level count has no capacity
    because the per-strain curves never plateaued, and capacity_source blamed the culture-level count."""
    client = CultureClient({"r1": ["fc"]})
    monkeypatch.setattr(derive, "replicates_for_experiment", lambda *a, **k: ([], []))
    culture, _ = derive.monoculture_rates(client, [_exp(["r1"])], identities={})
    ((nid, entry),) = culture.items()
    per_strain = {nid: {**entry, "values": entry["values"] * 3, "sources": {"per-strain": 3}}}
    (rate,) = derive.merge_rates([("S1", per_strain), ("S2", culture)]).values()
    assert rate["rate_sources"] == {"per-strain": 3, "culture-level fc": 1}, rate["rate_sources"]
    assert rate["capacity"] is None
    assert "culture-level" not in (rate.get("capacity_source") or "")
    # and alone, the count is still named (the control)
    (alone,) = derive.merge_rates([("S2", culture)]).values()
    assert alone["capacity_source"].startswith(derive.CULTURE_NONE)


def test_the_report_says_once_why_a_culture_level_rate_has_no_capacity(monkeypatch):
    """Round 3 of the review: the report printed the culture-level clause and then capacity_source, which
    says the same thing."""
    from grownet import report
    client = CultureClient({"r1": ["fc"], "r2": ["fc"], "r3": ["fc"]})
    monkeypatch.setattr(derive, "replicates_for_experiment", lambda *a, **k: ([], []))
    found, _ = derive.monoculture_rates(client, [_exp(["r1", "r2", "r3"])], identities={})
    (rate,) = derive.merge_rates([("S9", found)]).values()
    from grownet.model import InteractionNetwork
    net = InteractionNetwork()
    net.meta["growth_rates"] = {"rule": "r", "organisms": {"x": {**rate, "name": "X"}}}
    text = report.report_text({"network": net, "resolved": [], "unresolved": [], "studies": [], "errors": [],
                               "skipped": [], "entries": []})
    assert "culture-level fc (3 replicate(s))" in text, text      # said once
    assert "never gives a capacity" not in text, "and not again"


def test_the_payload_sends_no_capacity_curve_count_without_a_capacity():
    """Round 3 of the review: growth_rates.csv leaves capacity_curves empty where there is no capacity, and
    the payload fell back to capacity_n and sent 0, so R's glv_write wrote 0 for the same run."""
    from test_payload_v1 import PAIR, RATES, _net

    from grownet import matrix
    rates = {k: {**v, "capacity": None, "capacity_n": 0} for k, v in RATES.items()}
    rates = {k: {kk: vv for kk, vv in v.items() if kk != "capacity_curves"} for k, v in rates.items()}
    detail = matrix.glv_payload(_net(PAIR), rates)["growth_rate_detail"]
    assert {d["carrying_capacity_curves"] for d in detail} == {None}


def test_the_report_says_its_skip_lines_name_organisms_as_their_study_does():
    """Rounds 3 and 4 of the review (#24): the interactions use a strain's current name and the lines on
    what was skipped quote its study, so both headings say so; deleting either clause left the suite green."""
    from grownet import report
    from grownet.model import InteractionNetwork
    text = report.report_text({
        "network": InteractionNetwork(), "resolved": [], "unresolved": [], "studies": [], "errors": [],
        "entries": [], "skipped": [("A organism -> B organism [EXP_1]", "no growth (auc) in either set"),
                                   ("EXP_9", "no monoculture of the target")]})
    assert "pairs the data did not support (1), named as their study names them:" in text, text
    assert "notes on the data read (1), which are not pairs, named as their study names them:" in text, text


def test_a_rate_with_no_recorded_source_is_not_called_culture_level(monkeypatch):
    """Round 4 of the review: without the `sources and` guard, an entry recording no sources was said to be
    "from a culture-level , which never gives a capacity"."""
    client = CultureClient({"r1": ["fc"]})
    monkeypatch.setattr(derive, "replicates_for_experiment", lambda *a, **k: ([], []))
    found, _ = derive.monoculture_rates(client, [_exp(["r1"])], identities={})
    ((nid, entry),) = found.items()
    (rate,) = derive.merge_rates([("S1", {nid: {**entry, "sources": {}}})]).values()
    assert "culture-level" not in (rate.get("capacity_source") or "")


def test_the_report_keeps_a_culture_level_reason_it_has_not_already_said():
    """Round 4 of the review: a genus row carries no `rate_sources`, so the clause the report de-duplicates
    against is not there, and the capacity_source is the only reason it gives."""
    from grownet import report
    from grownet.model import InteractionNetwork
    why = derive.CULTURE_NONE + " fc count (3 replicate(s)), which never gives a capacity"
    net = InteractionNetwork()
    net.meta["growth_rates"] = {"rule": "r", "organisms": {"g": {
        "name": "G", "rate": 0.3, "unit": "1/h", "n": 3, "capacity": None, "capacity_source": why}}}
    text = report.report_text({"network": net, "resolved": [], "unresolved": [], "studies": [], "errors": [],
                               "skipped": [], "entries": []})
    assert why in text, text


def test_the_technique_setting_chooses_among_the_culture_level_counts_and_never_admits_od():
    """Karoline, 2026-10-14 (#292): the Technique setting keeps curves of it only, and #140 still decides
    which culture-level counts exist. r3 has plates and fc: with fc chosen it is fc (plates would win by
    `CULTURE_TECHNIQUES` order otherwise); with od chosen nothing qualifies, OD being no count."""
    from grownet.adapter import only_technique
    client = CultureClient({"r1": ["od", "fc"], "r3": ["plates", "fc"]})
    with only_technique("fc"):
        reps, _ = culture_trace_replicates(client, _exp(["r1", "r3"]), STRAIN)
    assert [(r.name, r.curve(STRAIN).technique) for r in reps] == [("r1", "culture-level fc"),
                                                                    ("r3", "culture-level fc")]
    with only_technique("od"):
        reps, skipped = culture_trace_replicates(client, _exp(["r1", "r3"]), STRAIN)
    assert reps == [] and all(why.endswith("measured by od, the Technique setting") for _, why in skipped)
