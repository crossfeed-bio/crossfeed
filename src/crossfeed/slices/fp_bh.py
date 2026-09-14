"""First slice: the FP/BH study, end to end.

The first concrete demonstration of the crossfeed seam per the KU Leuven collaboration: take one
mGrowthDB study, turn it into a single interaction network in the neutral format, attribute it at the
edge level, and emit it for Syntropa to consume.

  --live      fetch the real study (SMGDB00000004, published/open) from the mGrowthDB API and derive the
              interactions with the PROVISIONAL baseline (crossfeed.derive). Needs network.
  --fixture   run the downstream seam offline on a small SYNTHETIC example (no network, used by CI).
"""
from __future__ import annotations

import argparse
import json
import sys

from ..attribution import render_attribution
from ..mgrowthdb import records_to_network

FP_BH_STUDY = "SMGDB00000004"   # "Integrated culturing, modeling and transcriptomics..." (published 2025-06-29)


def _build(records, study_id, source_db):
    net = records_to_network(
        records, meta={"source_db": source_db, "study_id": study_id, "slice": "fp_bh"}
    )
    problems = net.validate()
    if problems:
        raise SystemExit("network invalid:\n  " + "\n  ".join(problems))
    return net


def build_from_fixture(records, study_id=FP_BH_STUDY):
    return _build(records, study_id, "mGrowthDB (fixture)"), []


def build_live(study_id=FP_BH_STUDY):
    from ..derive import derive_interactions
    from ..mgrowthdb import MGrowthDBClient

    records, skipped = derive_interactions(MGrowthDBClient(), study_id)
    return _build(records, study_id, "mGrowthDB (live)"), skipped


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the FP/BH first-slice interaction network.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--live", action="store_true", help="fetch the real study from the mGrowthDB API")
    src.add_argument("--fixture", help="path to a JSON list of interaction records (synthetic demo)")
    ap.add_argument("--out", help="write the neutral network JSON here (default: stdout)")
    a = ap.parse_args(argv)

    if a.live:
        from ..mgrowthdb import MGrowthDBError
        try:
            net, skipped = build_live()
        except MGrowthDBError as e:
            print(f"live fetch failed: {e}", file=sys.stderr)
            return 1
    else:
        with open(a.fixture, encoding="utf-8") as f:
            net, skipped = build_from_fixture(json.load(f))

    payload = net.to_json()
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(payload)
        print(f"wrote {a.out}: {len(net.nodes)} nodes, {len(net.edges)} edges")
    else:
        print(payload)

    print(render_attribution(net), file=sys.stderr)
    if skipped:
        print(f"\nskipped {len(skipped)} pair(s) the data did not cleanly support:", file=sys.stderr)
        for label, reason in skipped:
            print(f"  - {label}: {reason}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
