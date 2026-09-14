"""First slice: the FP/BH study, end to end.

The first concrete demonstration of the crossfeed seam per the KU Leuven collaboration:
take one mGrowthDB study, turn it into a single interaction network in the neutral format,
attribute it at the edge level, and emit it for Syntropa to consume.

The live pull is a TODO (see crossfeed.mgrowthdb). Run with --fixture to exercise the whole
downstream seam on a small SYNTHETIC example (not real experimental data).
"""
from __future__ import annotations

import argparse
import json
import sys

from ..attribution import render_attribution
from ..mgrowthdb import MGrowthDBClient, records_to_network

FP_BH_STUDY = "SMGDB00000004"   # the study Faust pointed to for the FP/BH pair


def build(records=None, study_id: str = FP_BH_STUDY):
    """Build and validate the FP/BH interaction network (from fixture records, or the live client)."""
    if records is not None:
        net = records_to_network(
            records,
            meta={"source_db": "mGrowthDB (fixture)", "study_id": study_id, "slice": "fp_bh"},
        )
    else:
        net = MGrowthDBClient().build_network(study_id, meta={"slice": "fp_bh"})
    problems = net.validate()
    if problems:
        raise SystemExit("network invalid:\n  " + "\n  ".join(problems))
    return net


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the FP/BH first-slice interaction network.")
    ap.add_argument("--fixture", help="path to a JSON list of interaction records (synthetic demo)")
    ap.add_argument("--out", help="write the neutral network JSON here (default: stdout)")
    a = ap.parse_args(argv)

    records = None
    if a.fixture:
        with open(a.fixture, encoding="utf-8") as f:
            records = json.load(f)

    net = build(records=records)
    payload = net.to_json()
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(payload)
        print(f"wrote {a.out}: {len(net.nodes)} nodes, {len(net.edges)} edges")
    else:
        print(payload)
    print(render_attribution(net), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
