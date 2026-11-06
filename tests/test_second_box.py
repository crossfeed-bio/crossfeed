"""The second box (media, experiments or studies) applies to every derivation, not to the comparison alone.

It reached `ReplicateDeriver` only: `derive_interactions` built the default deriver with the selection and
handed any other deriver every experiment, so under the integrated form naming a medium changed nothing,
while gLV mode's message says "Name one medium in the second box to keep a simulation to one environment"
(found in review, 2026-11-06; it predates 0.5.0).

The fixture: one study holding the same design in two media, Broth X and Broth Y. In each, A and B grow
alone and together, simulated from known coefficients (`test_integrated._simulate`), so both derivations
give an arc between A and B in each medium. Naming "Broth X" must keep the arcs of Broth X only, with the
monocultures they are compared against and fitted from.
"""
import pytest
from test_growth_rates import FakeClient, _context
from test_integrated import _simulate

from grownet.derive import derive_interactions
from grownet.integrated import IntegratedDeriver
from grownet.selection import parse

MEDIA = {"X": "Broth X", "Y": "Broth Y"}
# experiment ids as mGrowthDB writes them, since the second box reads an id by its form
CODES = {"Xa": "EMGDB000000901", "Xb": "EMGDB000000902", "Xab": "EMGDB000000903",
         "Ya": "EMGDB000000911", "Yb": "EMGDB000000912", "Yab": "EMGDB000000913"}


def _study():
    """(client, experiment ids per medium): monocultures of A and B and their co-culture, in each medium,
    with two replicates each."""
    bioreplicates, series, experiments = {}, {}, {}
    mono_a = _simulate([0.4], [[-4.0e-9]], [1.0e7])
    mono_b = _simulate([0.3], [[-3.0e-9]], [1.0e7])
    co = _simulate([0.4, 0.3], [[-4.0e-9, -2.0e-9], [0.0, -3.0e-9]], [1.0e7, 1.0e7])
    ids = {}
    cid = 1000
    for tag, medium in MEDIA.items():
        for kind, members, (times, values) in (("a", ["A"], mono_a), ("b", ["B"], mono_b),
                                               ("ab", ["A", "B"], co)):
            exp_id = CODES[tag + kind]
            ids.setdefault(tag, []).append(exp_id)
            reps = []
            for k in range(2):
                bid = f"{exp_id}r{k}"
                contexts = []
                for i, member in enumerate(members):
                    cid += 1
                    # the second replicate a little higher, so the two are not identical
                    series[cid] = [(t, row[i] * (1 + 0.01 * k), None) for t, row in zip(times, values, strict=True)]
                    contexts.append(_context(cid, member))
                bioreplicates[bid] = {"id": bid, "name": f"r{k}", "isAverage": False,
                                      "measurementTimeUnits": "h", "measurementContexts": contexts}
                reps.append({"id": bid, "name": f"r{k}"})
            experiments[exp_id] = {
                "id": exp_id, "studyId": "S1", "name": f"{'+'.join(members)} in {medium}",
                "description": f"{' and '.join(members)} grown in {medium}", "cultivationMode": "batch",
                "compartments": [{"mediumName": medium}],
                "communityStrains": [{"name": m} for m in members], "bioreplicates": reps}
    study = {"id": "S1", "name": "two media", "experiments": [{"id": e} for e in experiments]}
    return FakeClient(bioreplicates, series, {"S1": study}, experiments), ids


def _derive(deriver, selection):
    client, ids = _study()
    if deriver is not None:
        deriver.client = client
    records, skipped = derive_interactions(client, "S1", deriver=deriver, metric="growth_rate",
                                           selection=selection)
    return records, skipped, ids


def _experiments(records):
    return {e for r in records for e in r.get("experiments", ())}


DERIVATIONS = {"replicate": lambda: None, "integrated": lambda: IntegratedDeriver()}


@pytest.mark.parametrize("derivation", sorted(DERIVATIONS))
def test_naming_one_medium_keeps_that_mediums_arcs_under_every_derivation(derivation):
    # a positive control first: without a selection this design gives arcs in BOTH media, so a test that
    # finds only Broth X below is finding what the second box did
    everything, _, ids = _derive(DERIVATIONS[derivation](), None)
    assert _experiments(everything) & set(ids["X"]) and _experiments(everything) & set(ids["Y"])

    records, _skipped, ids = _derive(DERIVATIONS[derivation](), parse(["Broth X"]))
    used = _experiments(records)
    assert records, f"{derivation}: naming Broth X left no arc"
    assert not used & set(ids["Y"]), f"{derivation}: Broth Y's experiments {sorted(used & set(ids['Y']))}"
    # and the co-culture of Broth X is compared against (or fitted from) Broth X's own monocultures
    assert CODES["Xab"] in used
    assert used & {CODES["Xa"], CODES["Xb"]}


@pytest.mark.parametrize("derivation", sorted(DERIVATIONS))
def test_naming_the_co_culture_keeps_the_monocultures_it_is_compared_against(derivation):
    """Karoline, 2026-10-04: naming a co-culture also keeps its monocultures, "chosen by the existing
    matching rules", and the run says which came along. Under the integrated form they are what stage 1
    fits the rates from."""
    records, skipped, ids = _derive(DERIVATIONS[derivation](), parse([CODES["Xab"]]))
    used = _experiments(records)
    assert records and CODES["Xab"] in used
    assert not used & set(ids["Y"])
    came_along = [why for label, why in skipped if label == "monocultures kept alongside the experiments named"]
    assert came_along and CODES["Xa"] in came_along[0] and CODES["Xb"] in came_along[0]


def test_a_deriver_that_does_not_read_the_box_itself_is_given_the_selected_experiments():
    """A deriver plugged in with --deriver knows nothing of the second box: it is handed only what the box
    selects, with the reasons, rather than every experiment of the study."""
    from grownet.derive import Deriver

    class Seen(Deriver):
        name = "seen"

        def derive(self, study, exps):
            self.seen = sorted(e["id"] for e in exps)
            return [], [("seen", "ok")]

    client, ids = _study()
    deriver = Seen()
    _records, skipped = derive_interactions(client, "S1", deriver=deriver, selection=parse(["Broth Y"]))
    assert deriver.seen == sorted(ids["Y"])
    assert ("seen", "ok") in skipped
