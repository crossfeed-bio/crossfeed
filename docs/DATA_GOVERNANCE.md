# Data governance

grownet is built under a collaboration governance agreement between Syntropa and KU Leuven.

## Sources

mGrowthDB is open. grownet reads growth curves (monocultures, co-cultures and communities) from mGrowthDB
through its public API and derives the interactions itself; mGrowthDB holds no interactions.
See https://mgrowthdb.readthedocs.io/en/latest/api.html .

## Attribution at the edge level

Per-study licenses are respected by citing every study that supports a network at the edge level:
each edge names the studies behind it, and a network cites all of its supporting studies with their
licenses. This is preferred over bundling because it keeps the per-study terms clean and makes clear
exactly which measurements stand behind each edge. Adopted with K. Faust, 2026-09-14.

The per-study license is not currently exposed by the mGrowthDB study endpoint, so edges carry the study
id and url with the license left empty rather than guessed (the local page shows "license: see study"). Resolving where each study's license is
published, and wiring it into the `study_license` field, is a pending item to confirm with the mGrowthDB
side.

## Responses kept on disk

Since #182, grownet keeps what it read from mGrowthDB between runs and reuses it while the study's
`uploadedAt` is unchanged, which Karoline confirmed for the mGrowthDB team is coupled to study submission.
That puts mGrowthDB measurements on a reader's disk, so where they go is part of this agreement:

- they are written to the **user's own cache directory** (`~/Library/Caches/grownet` on macOS,
  `%LOCALAPPDATA%` on Windows, `$XDG_CACHE_HOME` or `~/.cache` otherwise), with `GROWNET_CACHE` to move
  them and `--no-cache` to keep nothing. **Never inside the repository**, where the guardrail gate refuses
  raw data;
- nothing kept there is ever committed, published or bundled into an output: the published outputs are
  unchanged, carrying derived numbers and study citations and no raw curves;
- they hold only what the public API served, so they are open data under the per-study terms above, and
  unpublished collaborator data is still never read by the tool at all (see below).

## The daily All network

The All network is derived from mGrowthDB once a day and published as an asset of the `all-network`
release, outside git (#96). It carries no raw growth curves, only derived nodes and arcs, and every arc
cites its studies. Its report, `all_report.txt`, is published alongside it and lists every study behind
an arc with its title and DOI, so each can be credited (Karoline, 2026-09-29).

## Unpublished collaborator data

Any unpublished interaction calls, media, or genomes shared by a collaborator are used only for the
agreed analysis. They are never ingested into the Syntropa corpus and never used to train any model.
Raw pulled or shared data stays out of version control: see `.gitignore` and the `no-raw-data`
guardrail in `checks/gate.py`.

## Outward sign-off

Nothing bearing a collaborator's name or affiliation goes public without their sign-off.
