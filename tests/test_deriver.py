"""The pluggable derivation seam: the baseline matches the pure function, and a custom method plugs in."""
from crossfeed.derive import BaselineDeriver, Deriver, derive_interactions, interactions_from_experiments

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


class _FakeClient:
    """A stand-in for MGrowthDBClient: serves canned study and experiment dicts, no network."""

    def __init__(self, study, exps):
        self._study = study
        self._exps = {e["id"]: x for e, x in zip(study["experiments"], exps, strict=True)}

    def get_study(self, study_id):
        return self._study

    def get_experiment(self, experiment_id):
        return self._exps[experiment_id]


def test_baseline_deriver_matches_pure_function():
    exps = [_mono(A, 0.30), _mono(B, 0.30), _co(A, B, "FP_BH", 0.66, 0.31)]
    study = {"id": "S"}
    assert BaselineDeriver().derive(study, exps) == interactions_from_experiments(study, exps, "S")


def test_custom_deriver_is_honored():
    class Stub(Deriver):
        name = "stub"

        def derive(self, study, exps):
            return ([{"tag": "stub", "study": study["id"], "n_exps": len(exps)}], [])

    study = {"id": "S", "experiments": [{"id": "E1"}]}
    client = _FakeClient(study, [_mono(A, 0.30)])
    records, skipped = derive_interactions(client, "S", deriver=Stub())
    assert records == [{"tag": "stub", "study": "S", "n_exps": 1}]
    assert skipped == []


def test_derive_interactions_runs_baseline_via_client():
    exps = [_mono(A, 0.30), _mono(B, 0.30), _co(A, B, "FP_BH", 0.66, 0.31)]
    study = {"id": "S", "experiments": [{"id": "E_" + A}, {"id": "E_" + B}, {"id": "E_FP_BH"}]}
    client = _FakeClient(study, exps)
    records, skipped = derive_interactions(client, "S")
    assert any(r["effect"] == "facilitation" for r in records)
    assert all("PROVISIONAL" in r["method"] for r in records)
