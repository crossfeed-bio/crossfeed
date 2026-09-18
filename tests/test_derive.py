"""Offline tests for the provisional baseline derivation (synthetic experiment dicts, no network)."""
from crossfeed.derive import _gs, interactions_from_experiments
from crossfeed.mgrowthdb import records_to_network

STUDY = {"id": "SMGDB_TEST", "name": "synthetic test study", "url": "http://example/study"}
A = "Faecalibacterium prausnitzii A2-165"
B = "Blautia hydrogenotrophica DSM 10507"


def _mono(name, gr):
    return {"id": "E_" + name, "name": name, "communityStrains": [{"name": name}],
            "bioreplicates": [{"name": "r1", "measurementContexts": [
                {"techniqueType": "fc", "subject": {"type": "bioreplicate", "name": name}, "growthRate": gr}]}]}


def _co(a, b, cond, gr_a, gr_b):
    return {"id": "E_" + cond, "name": cond, "communityStrains": [{"name": a}, {"name": b}],
            "bioreplicates": [{"name": "Average", "measurementContexts": [
                {"techniqueType": "qpcr", "subject": {"type": "strain", "name": a}, "growthRate": gr_a},
                {"techniqueType": "qpcr", "subject": {"type": "strain", "name": b}, "growthRate": gr_b}]}]}


def test_pairwise_derivation():
    # A alone 0.30; with B, A grows 0.66 (facilitated); B ~ unchanged (0.31)
    exps = [_mono(A, 0.30), _mono(B, 0.30), _co(A, B, "FP_BH", 0.66, 0.31)]
    recs, skipped = interactions_from_experiments(STUDY, exps)
    assert skipped == []
    net = records_to_network(recs, meta={"slice": "test"})
    assert net.validate() == []
    # B -> A is facilitation (0.66 vs 0.30 -> log2 > 1)
    ba = next(e for e in net.edges if e.source == _gs(B) and e.target == _gs(A))
    assert ba.effect == "facilitation" and ba.strength > 1
    # A -> B is neutral (0.31 vs 0.30 -> tiny log2, within the deadband)
    ab = next(e for e in net.edges if e.source == _gs(A) and e.target == _gs(B))
    assert ab.effect == "neutral"
    # every edge is qualitative (no significance test yet) and carries the provisional method note
    assert all(e.significance is None and "PROVISIONAL" in e.method for e in net.edges)


def test_missing_mono_is_skipped():
    # co-culture present but no mono for either strain -> both directions skipped, no fabrication
    exps = [_co(A, B, "FP_BH", 0.66, 0.31)]
    recs, skipped = interactions_from_experiments(STUDY, exps)
    assert recs == []
    assert all("no mono growth" in reason for _, reason in skipped)


def test_three_member_skipped():
    exps = [{"id": "E", "name": "ABC",
             "communityStrains": [{"name": A}, {"name": B}, {"name": "Roseburia intestinalis L1-82"}],
             "bioreplicates": []}]
    recs, skipped = interactions_from_experiments(STUDY, exps)
    assert recs == []
    assert any(">2 members" in reason for _, reason in skipped)


def test_baseline_edges_are_biculture_evidence():
    exps = [_mono(A, 0.30), _mono(B, 0.30), _co(A, B, "FP_BH", 0.66, 0.31)]
    recs, _ = interactions_from_experiments(STUDY, exps)
    net = records_to_network(recs)
    assert net.edges and all(e.evidence == "biculture" for e in net.edges)
    assert all(e.community == tuple(sorted([_gs(A), _gs(B)])) for e in net.edges)
