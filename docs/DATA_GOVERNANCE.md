# Data governance

crossfeed is built under a collaboration governance agreement between Syntropa and KU Leuven.

## Sources

mGrowthDB is open. crossfeed pulls co-growth interaction data from mGrowthDB through its public API.
See https://mgrowthdb.readthedocs.io/en/latest/api.html .

## Attribution at the edge level

Per-study licenses are respected by citing every study that supports a network at the edge level:
each edge names the studies behind it, and a network cites all of its supporting studies with their
licenses. This is preferred over bundling because it keeps the per-study terms clean and makes clear
exactly which measurements stand behind each edge. Adopted with K. Faust, 2026-09-14.

The per-study license is not currently exposed by the mGrowthDB study endpoint, so edges carry the study
id and url with the license marked unresolved rather than guessed. Resolving where each study's license is
published, and wiring it into the `study_license` field, is a pending item to confirm with the mGrowthDB
side.

## Unpublished collaborator data

Any unpublished interaction calls, media, or genomes shared by a collaborator are used only for the
agreed analysis. They are never ingested into the Syntropa corpus and never used to train any model.
Raw pulled or shared data stays out of version control: see `.gitignore` and the `no-raw-data`
guardrail in `checks/gate.py`.

## Outward sign-off

Nothing bearing a collaborator's name or affiliation goes public without their sign-off.
