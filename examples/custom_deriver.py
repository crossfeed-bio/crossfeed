"""A complete, runnable example of plugging a custom derivation method into crossfeed.

The derivation method is the scientific choice the collaboration makes (see docs/METHOD_NOTES.md). It
plugs in through the `Deriver` interface: one class, one method `derive(study, exps)` that returns
interaction records. This file defines a small illustrative Deriver, runs it offline on synthetic data,
and prints the neutral network. It is a template for the mechanics, not a recommended method.

Run it offline (no network):

    python examples/custom_deriver.py

Run YOUR Deriver live on a real study, with no glue code:

    python -m crossfeed derive SMGDB00000004 --live --deriver examples.custom_deriver:RelativeChangeDeriver
"""
from __future__ import annotations

from crossfeed.derive import Deriver
from crossfeed.mgrowthdb import records_to_network


def _growth(exp, strain=None, metric="growthRate"):
    """Read a strain's growthRate from an experiment: the community context for a monoculture
    (strain is None), or the per-strain context for a co-culture. Returns None if absent."""
    want = "bioreplicate" if strain is None else "strain"
    for br in exp.get("bioreplicates", []):
        for mc in br.get("measurementContexts", []):
            sub = mc.get("subject", {})
            if sub.get("type") == want and (strain is None or sub.get("name") == strain):
                return mc.get(metric)
    return None


class RelativeChangeDeriver(Deriver):
    """Illustrative method: an interaction is facilitation or inhibition when a strain's growthRate in a
    two-member co-culture differs from its monoculture by more than `threshold` (a fraction)."""

    name = "relative-change-example"
    method = "example: (co - mono) / mono against a fractional threshold; pairwise co-cultures only"

    def __init__(self, threshold: float = 0.15):
        self.threshold = threshold

    def derive(self, study, exps):
        monos = {}
        for e in exps:
            members = [s["name"] for s in e.get("communityStrains", [])]
            if len(members) == 1:
                g = _growth(e, None)
                if g is not None:
                    monos[members[0]] = g

        records, skipped = [], []
        for e in exps:
            members = [s["name"] for s in e.get("communityStrains", [])]
            if len(members) != 2:
                continue
            cond = e.get("name", "")
            for focal, partner in ((members[0], members[1]), (members[1], members[0])):
                mono, co = monos.get(focal), _growth(e, focal)
                if mono is None or co is None or mono <= 0:
                    skipped.append((f"{partner}->{focal} [{cond}]", "missing mono or co growth"))
                    continue
                change = (co - mono) / mono
                if abs(change) < self.threshold:
                    effect = "neutral"
                elif change > 0:
                    effect = "facilitation"
                else:
                    effect = "inhibition"
                records.append({
                    "source": partner, "target": focal, "source_name": partner, "target_name": focal,
                    "effect": effect, "strength": round(change, 4), "significance": None,
                    "condition": cond, "method": self.method, "study_id": study["id"],
                })
        return records, skipped


def _synthetic():
    """Two monocultures and one pairwise co-culture, in the mGrowthDB experiment shape."""
    a, b = "Strain A", "Strain B"

    def mono(name, rate):
        return {"name": name, "communityStrains": [{"name": name}],
                "bioreplicates": [{"measurementContexts": [
                    {"subject": {"type": "bioreplicate", "name": name}, "growthRate": rate}]}]}

    co = {"name": "A+B", "communityStrains": [{"name": a}, {"name": b}],
          "bioreplicates": [{"measurementContexts": [
              {"subject": {"type": "strain", "name": a}, "growthRate": 0.66},
              {"subject": {"type": "strain", "name": b}, "growthRate": 0.29}]}]}
    return {"id": "SYNTH", "name": "synthetic example"}, [mono(a, 0.30), mono(b, 0.30), co]


def build_example_network():
    """Run the illustrative Deriver on the synthetic data and return the validated network."""
    study, exps = _synthetic()
    records, _ = RelativeChangeDeriver(threshold=0.15).derive(study, exps)
    net = records_to_network(records, meta={"source_db": "synthetic", "study_id": study["id"]})
    assert net.validate() == [], net.validate()
    return net


def main():
    net = build_example_network()
    print(net.to_json())


if __name__ == "__main__":
    main()
