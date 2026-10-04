# Agent notes (shared memory)

This is the handoff file between agent sessions. Read it at the start of a session and update it in the
same pull request as your change.

Rules for this file:

- Record what is not obvious from the code, the git history, or the issues: decisions and their reasons,
  dead ends, quirks of external systems, open questions.
- Edit in place. Replace stale entries instead of appending contradictions. This is not a session log;
  the history lives in commits and pull requests.
- Date each entry (YYYY-MM-DD) and link the issue or pull request when there is one.
- Tasks do not go here. They are GitHub Issues.
- The repository is public and the house style gate applies (see [AGENTS.md](../../AGENTS.md)).

## Current state

- 2026-09-28 (Craig, #71): the schema id is `grownet.interaction_network/v0`. A new namespace at the SAME
  version, because the format is not changing and a version is a promise about content, not about naming.
  Done before 0.1.0 deliberately: the id is written into every network grownet saves, so this is the last
  moment it costs nothing. Nothing has been released, so no published file carries the old id, and
  `validate_document` is left strict rather than accepting both. Two ids for one format would be the same
  defect the corpus side spent this week guarding against, and a reader who does hold an older test file
  gets an exact message naming both ids. The repository address and the method labels are separate and
  still Craig's.
- 2026-09-28 (Karoline): the command line "should be called grownet". Renamed: package, module and command
  are `grownet` (src/grownet), with no `crossfeed` alias. Unchanged, on purpose: the repository address
  (crossfeed-bio/crossfeed, Craig's call), the
  method labels stored in networks ("crossfeed replicate v1", "crossfeed baseline v0"), LICENSE and NOTICE
  ("The crossfeed authors", a legal line for Karoline and Craig to change), and the history in
  CHANGELOG, METHOD_NOTES and this file. After pulling, reinstall (`pip install -e ".[dev]"`) and remove a
  stale install (`pip uninstall crossfeed`).
- 2026-09-28 (Karoline): "for me, project implementation is now complete and so focus can be on
  auditing/testing." New features are not proposed unprompted; the work is auditing, testing against
  mGrowthDB, and fixing what that finds. Still to come: the rename (#71) and the 0.1.0 release
  (RELEASING.md).
- 2026-09-17: v0.0.2 is unreleased on `main`. The pipeline runs end to end on live mGrowthDB data with
  the provisional `BaselineDeriver`. CLI: `derive`, `validate`, `schema`; outputs JSON and GraphML.
- 2026-09-17: Helpers `crossfeed.growth` and `crossfeed.interaction` are merged (#9, feature #3). Karoline's
  account has write access; the labels `feature`, `task`, `needs-decision`, `method`, and
  `agent-generated` exist, and sub-issues can be attached.
- 2026-09-18: added `gui/`, a self-contained HTML viewer (presentation layer: reads the neutral format,
  filters by species, shows edge provenance, downloads JSON and the same GraphML `export.py` writes).
  Rewrote `docs/METHOD_NOTES.md` to describe the baseline as it actually runs and to record opening
  default votes for Karoline and Haris to settle.
- 2026-09-18: merged the taxonomy resolver (#21), drop-out interaction strengths and the obligate and
  abolished outcomes (#16), the optional `evidence` and `community` edge fields (#17), and the local
  `crossfeed gui` server (#22). The default derivation is unchanged by all four: each adds capability the
  settings in METHOD_NOTES can later switch on.

## Decisions

- 2026-09-14: Attribution is at the edge level (each edge cites its supporting studies) rather than
  bundling licenses. See [docs/DATA_GOVERNANCE.md](../DATA_GOVERNANCE.md).
- 2026-09-17: Agent workflow set up: instructions in `AGENTS.md`, shared memory in this file. Features
  (human) and tasks (sub-issues) live in GitHub Issues, not in a master file, because contributors
  without write access can still open and comment on issues, and parallel agents do not conflict. Roles:
  mayor, worker, verifier. The repository is an agreed experiment in agent-based programming.
- 2026-09-17: An account with read-only access cannot attach sub-issues: `gh issue create --parent N`
  creates the issue but fails on `addSubIssue`. Without triage or write access, the mayor lists the
  tasks in a comment on the feature and writes "Feature: #N" in each task (as on #3).
- 2026-09-17: Without write access, dependent tasks go out as stacked pull requests from a fork, each
  based on `main`; the description says to merge in order and review only the last commit.
- 2026-09-17: `main` requires one approving review, and GitHub never lets a pull request's author
  approve it. A pull request opened by an agent under a person's account therefore needs a review from
  someone else (another collaborator or their agent).
- 2026-09-17: Collaborators with write access push branches to this repository, not a fork, so CI
  runs without maintainer approval and later branches can stack on earlier ones.
- 2026-09-18 (Karoline): species and strain names are resolved through mGrowthDB, never by querying NCBI
  directly. mGrowthDB is linked to NCBI through a local import that is kept up to date, so following its
  naming keeps one source of truth. The current name for a taxon id is the one in the most recently
  published study holding it (#24).
- 2026-09-18 (Craig, on merging #17): the optional `evidence` and `community` edge fields are accepted
  into the neutral format (item 4 of "Open decisions"). `evidence` is `biculture` (mono versus bi-culture,
  direct) or `dropout` (possibly indirect), and `community` records the members of the full community.
  Both are optional, so the change is backward compatible for downstream readers.
- 2026-09-19 (Karoline, item 15): the pipeline derives through the comparison she specified. Her words:
  "go with your recommendation". So the mGrowthDB to `Replicate` adapter is built, `interaction.py`
  becomes the engine, and `derive.py` shrinks to that adapter behind the `Deriver` seam. This carries
  items 1 and 12 with it: the replicate set comparison is adopted, and every edge gains a standard error
  and replicate counts. Her agent claimed the work so it would not be built twice (#34, #35, #36).
- 2026-09-19 (Karoline, item 11): both growth metrics ship. Her words: "both should be supported by the
  method, with a sensible default (AUC) but users should be able to switch to growth rate. There can be
  checks in place to avoid zero growth rates (see item 5)." AUC is the default, `max` is selectable, and
  growth rate joins as a third entry in `growth.FEATURES` once a stated rule for it exists (#41).
- 2026-09-19 (Karoline, item 5): no growth is a test across replicates, not a detection limit. Her words:
  "we have no systematic knowledge of detection limits. For growth, if there are replicates and there is
  no significant difference between start abundance and maximum abundance, then it's no growth." It feeds
  the existing `no_growth`, `obligate` and `abolished` outcomes. Two things stay open for us: which test
  and its alpha (the same choice as item 10), and what to do when a set has no replicates to test with.
- 2026-09-19 (Karoline, item 7): mGrowthDB will not expose species-rank or higher taxa. Her words: "not
  planned, primarily because experiments happen with concrete entities (strains), not abstractions. In
  future, we may include that for easier querying, but there's no active development now." So a node
  carries `taxon_id` and a `rank`, and the species-level key has to come from somewhere other than the
  database.
- 2026-09-19 (Karoline, item 8): the shared node key is derived from the genus and species of the name,
  and the node says so rather than implying a taxonomy lookup happened. A cached NCBI lookup for the
  species-rank ancestor stays available as the upgrade if the mGrowthDB-only naming rule is ever relaxed,
  and matching at strain rank is the guarantee the README should state for any consumer. Open for Haris:
  whether microbetag can meet crossfeed at strain rank, which would make the derived species key a
  convenience rather than the join column.
- 2026-09-19 (Karoline, outlier replicates): a replicate whose curve carries an implausible spike is
  flagged, never dropped silently, with the factor an advanced setting (#39). Found by running the
  specified comparison on SMGDB00000004: one qPCR trace (BH_14, context 3465) holds two consecutive
  points at 5.264e13 cells/mL between neighbors of 1.06e8 and 4.84e8, which moved B. hydrogenotrophica's
  standard error to 3.5 on a log2 scale.
- 2026-09-19 (Karoline): items 10, 13 and 14 of "Open decisions" are deferred until the settled items
  above have landed.
- 2026-09-20 (Craig, item 2): drop-out arcs enter the default network, labeled by evidence with the
  community recorded, as the default value of a user setting. Karoline's own words (2026-09-18) put
  "whether or not to include drop-out communities" among the advanced settings that "can be given
  sensible default values", so the setting exists either way and Craig's call is what its default is.
  His call on the default, not a ratification of a stated position on inclusion: the register
  attributes "keep these arcs, labeled by evidence" to Karoline, but that line is her agent's
  characterization, is not quoted anywhere in her own words, and carried "to confirm with Craig" when it
  was written. She settled eight register items on 09-19 without settling this one. The wording also has
  two readings, produce and label them, or include them by default, and only the second is a change here.
  RESOLVED 2026-09-21 (Karoline, her own words, given 2026-09-17 and confirmed on #34): "I'd still like
  to include these arcs, because they are still informative, but any arcs in the interaction network
  coming from drop-out communities should be labeled as such." That is the second reading, so her
  position and Craig's decision agree. The paraphrase carried her meaning; the quotation now replaces it.
- 2026-09-21 (Karoline, item 19): an edge's effect label follows its spread, not a fixed band, using the
  standard deviation rather than the standard error because sd does not shrink as replicates are added.
  mean plus or minus sd entirely above zero is facilitation, entirely below is inhibition, and a crossing
  interval on an edge with no quality flags is neutral, meaning an absence of interaction. An edge with
  any quality flag keeps the sign of its mean and is flagged rather than called neutral, because low
  quality and absence of interaction are different things. The sd rule stands in for a statistical test
  until item 10 settles one. The fixed 0.25 deadband retires with `BaselineDeriver`.
- 2026-09-21 (Karoline as method, Craig as the format contract, item 20): edges carry a `quality` list
  saying what is wrong with them, and `sd` alongside `se`. Both optional and backward compatible, like
  `evidence` and `community`; the schema is regenerated from the model. Flags so far: a single replicate,
  a spread crossing the sign, an outlier replicate (#39), pooled strains (until #23), non-batch
  cultivation (#42).
- 2026-09-21 (Karoline, item 21): neutral edges and low-quality edges are both computed and both hidden
  by default, each behind its own display setting. The filter applies at output, not in the derivation,
  and the network's `meta` records which filters were applied so a reader of a file knows what is missing.
- 2026-09-21 (Karoline): #39, the outlier rule, merges before #40, and #40 rebases onto it, so the
  default deriver never ships with the SMGDB00000004 qPCR artifact inside a monoculture set.
- 2026-09-21 (Karoline, item 19 revised): there is no neutral edge. Her words: "'neutral edge' is
  contradictory; the neutral case is the true absence of an edge." Refined the same night (see the
  absence threshold entry below): a comparison below the threshold is exported as an edge with `status`
  absent, not kept apart in `meta.absent`, so a measured "we looked and found nothing" reaches Cytoscape
  too. `neutral` remains in the format only for the retired baseline and for networks already derived.
- 2026-09-21 (Karoline, item 10): a statistical test is reported, not used to decide. Her words: "let's
  drop the significance test as a decision-making tool but keep its result in an edge attribute, since a
  significant result supports an edge (whereas a non-significant result is not informative)." Welch's
  t-test on the per-replicate log2 values, with Benjamini-Hochberg across every comparison in one
  derivation. `p_value` holds the raw value, `significance` the adjusted one.
- 2026-09-21 (Craig, the format): `p_value` and `meta.absent` accepted, after `sd`, `quality` and
  `notes`. All optional and backward compatible; the schema is regenerated from the model.
- 2026-09-21 (Karoline, the dependence judgment item 3 left open): Benjamini-Hochberg is the default,
  since it holds under positive regression dependence and the replicate reuse item 3 describes is
  plausibly positive; Benjamini-Yekutieli, which holds under any dependence, is a setting
  (`--correction by`). Her words: "Fine for your proposal on BH vs BY." `meta.statistics` names the one used.
- 2026-09-21 (Karoline, the absence threshold, option B): absences reach Cytoscape as edges. Her words:
  "in the exported network, assign an edge weight reflecting the strength of the edge based on the log2
  ... we'd keep the edges but do not visualise/report them by default"; "the status 'absent' depends on a
  user-defined threshold with a sensible default already set in the tool"; "meta.absent is not needed";
  "OK for option B, but it has to be carefully documented." Every tested comparison is an edge with
  `weight` (|log2 mean|, always positive), `effect_over_sd` (|log2 mean| / sd) and `status`, `absent` when
  |log2 mean| < k * sd, default k = 1 (the mean plus or minus sd rule), 0 marking nothing absent. The
  Cytoscape style hides absent edges by default; a column filter on `effect_over_sd` reproduces any k.
  Obligate and abolished edges are the extremes of each direction, always present, with their own style.
  Low-quality edges are not exported by default. This closes the gap that a tested absence did not reach
  GraphML. The three new edge fields replace `meta.absent` and need Craig's acceptance as a format change.
- 2026-10-03 (Karoline, amending option B): absent arcs are left out of every output by default. Her
  words: "The arc number reported in Cytoscape is not identical to the arc number we see because of hidden
  arcs. This can be confusing", then "maybe do not export hidden arcs (in any network) and only report them
  in the results", and on the three options offered, "OK, please go for 2": one setting, off by default,
  across all outputs. So `select_edges` drops them and counts them in `meta.hidden.absent`;
  `meta.absence.absent` still says how many the threshold marked, whether or not they ship; the page keeps
  its own section for them (built from the records, not the network) and the report says how many were
  left out. `--include-absent` and the matching checkbox put them back, which is option B's behavior and
  what lets a reader retune k in Cytoscape on `effect_over_sd`. Tests that are about other rules pass
  `include_absent=True` so they keep checking what they claim.
- 2026-09-21 (Karoline, drop-out designs, #47): experiments are pooled only when they are replicates.
  Her words: "if both experiments are replicates (performed with the same medium and settings) then they
  can be treated as such. if not, these would have to be treated as different arcs, since interactions
  are usually environmentally specific. we could support multi-arcs, i.e. interactions supported by
  different experiments." Filtering by environment is a separate discussion (#61); by default nothing is
  filtered. A positive signal for the removed member in a drop-out experiment makes that drop-out's arcs
  unreliable (flag `removed_member_detected`). Exactly two replicates on a side gets a flag, "I'd go for the
  quality flag", which she chose as a caution (`two_replicates`) that does not hide the edge or undo its
  status. On dependence: "such arcs should have an attribute whose value is the experiment of origin and a
  flag that they come from a drop-out experiment" (`experiments`, and `evidence: dropout`). Pairwise and
  drop-out arcs for one pair are parallel arcs: "yes, multi-arcs. could be condensed into an arc with a
  number-of-studies-supporting-the-arc attribute", which is the merge step of register item 10. Arcs come
  from whichever drop-outs exist ("agree"). Drop-out arcs get their own Cytoscape style (#25).
- 2026-09-21 (Karoline, on #62): each drop-out arc has its own window ("alright, per arc"). On pooling:
  "RI_BH +Ac" and "RI_BH -Ac" "do have different conditions: 1 contains acetate, the other doesn't";
  mGrowthDB "does not detail medium components well", and combining similar but not identical conditions
  "could be allowed later, but would need a good description of the conditions. Not for now." So
  experiments pool only when their descriptions also agree apart from a trailing run number. Obligate
  edges must not be hidden "just because they don't have the measurements on one side by definition":
  the side without growth counts its replicates without growth.
- 2026-09-21 (Karoline, on #62): "Yes to the spike guard": a spike is one or two consecutive interior points
  above both neighbors by the factor, replacing the maximum over the median, which flagged die-offs and
  late growth in SMGDB00000013 and SMGDB00000014. The first and last points are never a spike. Edge case
  she named: "perturbations may explain spikes, but right now only occur in chemostats"
  (SMGDB00000005). On line styles: "Cytoscape supports different dash styles", so single-replicate and
  drop-out arcs get different dash patterns (#25).
- 2026-09-21 (Karoline, #23): "taxon id should be strain level. That requires a node label with the name
  of the strain to keep the network readable." Nodes are `ncbi:<taxon id>`, named with the strain name;
  monocultures match co-cultures by id. An id given to different strains in one study (SMGDB00000008:
  1506553 for both L. clostridioforme 2_1_49FAA and L. symbiosum WAL-14673) falls back to genus and
  species and is reported, as is a record without an id.
- 2026-09-21 (Karoline, on #62): single-replicate edges are shown by default: "change the default
  treatment for the single_replicate case and to show those edges but take care in the cytoscape style
  that they are marked somehow, e.g. dashed." They keep the `single_replicate` flag and an undetermined
  status; strains_pooled, removed_member_detected and non_batch stay hidden by default. Study 8's missing
  biological replicates are for mGrowthDB to fix: "We can't start correcting data in the tool; this needs
  to happen in mGrowthDB." Karoline has noted it for mGrowthDB development.
- 2026-09-27 (Karoline, on #68, the no-growth rule of item 5): her words: "yes to all 3, as long as the
  maximum in the paired test can come from different time points (since the time of maximum abundance may
  vary across replicates)." The three were her agent's proposals: keep the twofold half at a factor of 2;
  make alpha and the factor settings and record them in the network (Craig's agent's request); test with
  a paired test on each replicate's log2(maximum / start) instead of Welch on unrelated samples.
  Revised the same day, her words: "I'd put the factor (which defines growth) as an advanced option. the
  default can be medium (1.5) and it can be made more stringent by the user (e.g. set to 2)." So
  `NO_GROWTH_FACTOR` is 1.5. Measured on six live studies, 1.5 admits three sets more than 2 does, all
  sustained rises of 1.7 to 2 times, none a single noisy point.
- 2026-09-27 (Karoline, conditions recorded only in descriptions, METHOD_NOTES item 22): "yes to 1-3,
  and 4 is noted". Monocultures pool only when their descriptions agree (`_mono_index` keys on
  `run_group`); several candidate sets: the one whose description quotes the co-culture's name
  (`_choose_monocultures`), then the one whose name has the same qualifier (`_qualifier`: the words
  before the last, "Evolved AtCt" -> "evolved"; Karoline: "yes"), else the pair is skipped; description-only
  variants of a pair or a drop-out design get the caution `conditions_unverified`, unless a member's set
  was matched by name or qualifier.
- 2026-09-27 (Karoline, METHOD_NOTES item 23): a monoculture is compared with a co-culture only when both
  use the same species-identifying technique, even when another technique gives the same unit.
  `growth.check_sets` requires one `GrowthCurve.technique` per species across the sets compared; the
  adapter fills it from `techniqueType`. Whole-culture traces stay out of monoculture comparisons.

## Genus merging, genus queries and All (2026-09-28)

Karoline's requests and choices are in METHOD_NOTES items 24 and 25, in her words. For agents: the genus
rule is `model.genus_name` (first word after the qualifiers Candidatus, unclassified and uncultured;
NCBI's brackets kept, so [Clostridium] is not Clostridium), shared by the genus colors, the merge and the
genus query, so they cannot disagree. `derive.merge_genus` runs after `merge_parallel` in
`output_meta`. `gui.support_level` decides species or strain pairs. `SpeciesIndex.studies` lists every study
the crawl found, which All derives. Names decide the genus: Phocaeicola (former Bacteroides) stays apart.
## Release (2026-09-27)

Karoline's answers on the first release, in her words: the rename "Wait for #79 first"; version
"0.1.0"; builds "Windows only" (no macOS or Linux program: those users install with uv or PyPI);
publishing "I prepare, you and Craig publish". So the agent prepares everything, and a person sets up
PyPI trusted publishing, approves the `pypi` environment and pushes the tag (RELEASING.md). Order: #79,
the rename (#71), the release pull request, the tag. Windows ships unsigned first (a one-folder zip,
Karoline on #63), then the SignPath Foundation, which needs an existing release, then perhaps the
Microsoft Store; a certificate is never bought (#63). Verified: the zip builds on a Windows runner
(9 MB), starts, serves the page and derives the fixture; the wheel installs and starts in a clean
environment.

## Open questions (need a human)

- Method and format questions are collected in "Open decisions" in
  [docs/METHOD_NOTES.md](../METHOD_NOTES.md).
- Where each mGrowthDB study's license is published; the study endpoint does not expose it, so
  `study_license` is marked unresolved.

- Signing and SmartScreen, which is easy to get wrong in both directions. A purchased certificate does
  not clear the warning on a new binary, so paying for EV to avoid it is wasted. But signing does matter:
  reputation cannot carry from one release to the next unless both are signed by the same publisher, so
  unsigned builds restart from zero forever, and Smart App Control on Windows 11 blocks unsigned
  executables rather than warning about them. The SignPath Foundation signs open-source projects free.
  The Microsoft Store removes the warning entirely, signs the app itself, and its registration is now
  free. See METHOD_NOTES item 9 for the full comparison.

## Color and readers with a color vision deficiency

Facilitation is green #1A7F5A, inhibition orange-red #C2410C, an absent edge gray #8A8A8A, in the legend,
the Cytoscape style and the mark. The orange replaced a plain red on 2026-09-27, when Karoline made the arc
tips uniform: the color became the only cue for the sign, and green against red is the pair a reader with a
color vision deficiency finds hardest. `tests/test_palette.py` simulates protanopia and deuteranopia
(Vienot 1999) and requires the two to stay 70 sRGB units apart; they manage 87 and 97, where green and red
managed 58. It also checks that both read as text on white and that the legend and the style use one
palette. Gray is separated from both by lightness, not hue, and an absent edge is thinner and hidden by
default, so color is never its only cue.

## Showing the sign

The Cytoscape style draws no edge labels (Karoline, 2026-09-27: the sign "should not be displayed by
default but should of course be an edge attribute"). Every edge already carries `strength` (the signed
log2 mean), `effect` (the word) and `weight` (its magnitude), so a user maps Label to `strength` in the
Style tab when they want it drawn. Nothing in the tool has to change for that.

## The mark

`docs/logo.svg` and `legend.LOGO`: three gray nodes joined by directed edges, one green (facilitation) and
one red (inhibition), both ending in the same arrowhead. Karoline chose it on 2026-09-27 from three
variants, with the rule that follows from it: **arc tips are uniform everywhere, and the color alone
distinguishes a positive from a negative effect**, in the legend and the Cytoscape style alike. Gray nodes
keep the two signal colors meaning one thing each. The page embeds the mark as a data URI, so nothing has
to be packaged or fetched. Open for her: green and red are the hardest pair for a reader with a color
vision deficiency, and with the heads now identical the color is the only cue.

## Legend

`src/crossfeed/legend.py` draws the legend; `docs/legend.svg` is its output (`make legend`) and the README
embeds it. `tests/test_legend.py` requires the drawing to name every value of EFFECTS, OUTCOMES,
QUALITY_FLAGS, CAUTIONS, EVIDENCE and STATUSES, and the shipped file to equal what the code draws. Adding a
flag therefore means adding a line to the legend, the same way Craig's viewer guard works (#57). The dash
patterns are the ones the Cytoscape style will use (#25): long dashes for drop-out evidence, dots for a
single replicate.
## Merging parallel arcs (register item 14, 2026-09-27)

`derive.merge_parallel` runs at the output stage, after status and filters (`output_meta(...,
merge_arcs, min_studies)`), so no single arc's numbers change. Off by default. `_merged` builds the arc; a
merged record lists `studies` (dicts), which `records_to_network` turns into several `study_ids`. With
merging off and `min_studies` 1 the edges pass through untouched (records need no source or target then).
On 2026-09-27 no pair in mGrowthDB had arcs from two studies, so `min_studies` 2 gives an empty network.

## Reading only what a search needs (2026-09-27)

`derive.relevant_experiments(exps, keep)` is the one rule for what a search with "only the species
entered" reads: monocultures and two-member co-cultures of kept strains, and every experiment of a drop-out
design with at least two kept members. Designs are kept whole because `_common_start` takes the most common
first time point over the full community and all its drop-outs, so leaving one out could change which
replicates are compared. Strain identities and description variants still come from every experiment.
`gui.run_query(..., narrow=False)` reads everything; eight live searches gave identical networks both ways.

## Growth rate metric (#41, built 2026-09-27)

`crossfeed.rates`: `easylinear` reimplements growthrates' fit_easylinear (windows of h points starting at
points 1 to N minus h, steepest slope, widened to every window within quota 0.95 of it, refit), and matched mGrowthDB's
reported growthRate on 190 of 192 curves within 10% (SMGDB00000002, 4, 7, 13; median ratio 1.00 each);
keeping growthrates' loop, which skips the last possible window, matched better on study 13. `baranyi` is the prototype's
guarded Levenberg-Marquardt fit (multi-start, mu within 5x the steepest slope, R2 >= 0.9); a rejected fit
raises `RateUnavailable`, and `interaction._log_values` leaves that replicate out with the reason, never
as no growth. Metric names carry the rule: "growth_rate:easylinear:5", "growth_rate:baranyi"
(`gui.metric_name`, `rates.method_name`). Karoline decided the implementations on #41 (2026-09-19) and
asked for the implementation as its own option (2026-09-27); easylinear is the default because it
reproduces mGrowthDB's numbers.

## Speed: parallel prefetch (2026-09-27)

Nearly all of a search's time was waiting on requests made one after another (about 100 ms each; 839 for
a cold Example). `crossfeed.fetch.prefetch_studies` reads, WORKERS (6) at a time, exactly what the
derivation will read (study, experiments, batch-only bioreplicates, one series per strain context) into
the client's in-memory cache; the derivation then runs unchanged. `species_index` crawls the same way and
walks the results in id order, so the first name seen per taxon is unchanged. The client keeps one
connection open per thread (`_connection`, `_send`) and retries JSON and CSV through one path
(`_request`). Verified against the sequential version on all studies: identical records, skip reasons and
index. A cache across sessions was ruled out: mGrowthDB shows only a study's latest version, and its change
history is not in the API, so a stored copy cannot tell it is stale (Karoline). A test double without
`get_study` and friends gets the one-by-one path (`fetch.can_prefetch`).

## The All network, derived once a day (2026-09-28, #96)

All is the one query whose cost grows with the whole of mGrowthDB (1,313 requests today, after #95), so
`.github/workflows/all-network.yml` derives it once a day with `DEFAULTS` (`packaging/publish_all.py`,
which refuses to publish a derivation with errors) and uploads `all_result.json` to the `all-network`
release. `grownet.published` reads it back: `usable` (the settings are the defaults), `fresh` (its format
and schema are this version's, and it is less than `MAX_AGE`, one day, old) and `fetch` (None on any
failure, so the caller derives live). `run_query(..., published=True)` tries it first; the publishing
script passes `published=False`, and so does `--no-published`. `tests/conftest.py` stubs `fetch` so no
test reaches GitHub; `fetch_from` takes the opener and the clock. This is a cache across sessions, which
was ruled out above for species searches; for All, Karoline asked for it with a bound: "serve from there
if less than a day old". Users' copies only read: writing would need a credential in every copy.

## Cytoscape (CyREST) quirks

- Applying a style or a layout is a GET (`/v1/apply/styles/{name}/{suid}`, `/v1/apply/layouts/...`); a
  POST gets 405. The first version posted, swallowed the error, and every network arrived unstyled
  (found by Karoline, 2026-09-27). The fake CyREST in `tests/test_cytoscape.py` now refuses that POST too.
- Posting a style whose title exists makes Cytoscape add a renamed copy (grownet_0). So `_ensure_style`
  updates an existing grownet style in place: PUT defaults, then DELETE each mapping by visual property
  (`/styles/{name}/mappings/{vp}`), then POST the mappings. DELETE on `/styles/{name}/mappings` as a whole
  is refused (405): that made every second send of a session arrive unstyled until it was found live.
  Verify both paths live, a first send (style created) and a second (style updated).
- Node colors are a per-network `genus_color` column with a passthrough mapping, so one shared style
  never recolors an earlier network. Colors: `brand.GENUS_COLORS`, validated with the dataviz palette
  script together with the two arc colors; each genus its own color (Karoline, 2026-09-27), from a list of
  48 picked greedily for separation (see the comment on `brand.GENUS_COLORS`).
- Verify against the real app by reading back view properties: `GET /v1/networks/{suid}/views/{view}/
  nodes?visualProperty=NODE_FILL_COLOR` (and the same for edges).

## Page style and name

`src/crossfeed/brand.py` holds the tool's name (`NAME` = grownet), the command users type today
(`COMMAND` = crossfeed, until the package rename of #71 flips it), the mark (the same SVG as `legend.LOGO`
on the Cytoscape branch, #70; the legend should take it from brand once both are merged), the palette and
the page CSS. The style is the one Karoline approved on 2026-09-27 ("The interface looks good"), with the
inhibition color she chose later (#C2410C). Every page goes through `gui._page(body, token)`, which adds
the header; the legend is served inside it (`render_legend`), not through `legend.legend_page`.

## The one page, progress and outputs

A search is a job (#75): `_Handler._start` runs `run_query` in a thread with a `progress(done, total,
message)` callback, and the POST redirects (303) to `/?job=ID`, which shows `render_progress` (a native
`<progress>` and a one-second meta refresh) until the job is done, then `render_result`. The POST first
waits `_Handler.wait` (1 s) so a quick search skips the progress page; tests set it to 0.05. Every page
with a result is `render_form(..., below=...)`, so the result sits under the settings (#74). The outputs
(#76) are `_outputs`: a GET form to `/download?format=json|graphml`, the POST to `/cytoscape`, and a
`details` holding `report.report_text`, also served at `/report.txt`. `tests/test_interface.py` quotes
Karoline's words for these and checks each through the running server; see AGENTS.md before changing it.

## Help page

`src/crossfeed/help.py` holds the help page as data keyed by the code's own names (#78):
`SETTINGS` by `gui.DEFAULTS` key, `EDGE_ATTRIBUTES` and `NODE_ATTRIBUTES` by model field, `CLI_ONLY` for
`derive` options that are not page settings. `tests/test_help.py` requires an entry for every setting,
every `derive` option (read from `__main__.build_parser`) and every model field, and requires the
attribute text to name every value of the model vocabularies. So a new setting, flag or field needs its
help line in the same change, the same way the legend works. The settings are a `dl`, not a table, and
field names break only after underscores (`<wbr>`), so the page has no horizontal scroll at phone width.
`records_to_network` starts `meta` from `mgrowthdb.provenance()` (tool, version, date); the report of
#76 reads them from there.

## Cultivation mode

`crossfeed.derive.cultivation` reads `cultivationMode` per experiment; `_batch_only` keeps batch unless
`include_non_batch` is set, and reports the rest with their mode (#42). The mode is part of `conditions`,
so a design never mixes modes. Test fixtures must declare `"cultivationMode": "batch"` or they derive
nothing, which is the point of the rule.
## Cytoscape (#25)

`crossfeed.cytoscape` posts Cytoscape.js JSON to CyREST. Verified 2026-09-27 against a real Cytoscape
3.10.3 on macOS: SMGDB00000004 arrived with 3 nodes and 20 edges, every attribute as a column, and all
seven style mappings live on the view (EDGE_VISIBLE, EDGE_TARGET_ARROW_SHAPE, EDGE_WIDTH, NODE_LABEL,
EDGE_LINE_TYPE, EDGE_STROKE_UNSELECTED_PAINT, EDGE_TARGET_ARROW_UNSELECTED_PAINT).

Two things learned there:

  * Cytoscape does not refuse a style whose title it already holds: it renames the new one (`crossfeed_0`),
    so a second run piles up copies. `send` asks for the style list first and leaves an existing style
    alone, since the user may have adjusted it.
  * One column maps to one visual property, so the two dash channels (drop-out evidence, single replicate)
    and the missing width of obligate and abolished arcs are computed into the `line_style` and
    `display_weight` columns instead of being layered as several mappings.

## The no-growth rule

`crossfeed.interaction.grew` decides whether a species grew in a replicate set, before any ratio is
computed (#37, register item 5, settled on #68). One rise per replicate, log2(maximum / first time
point), each maximum at its own time; grown when a paired t-test finds the rises above zero
(`NO_GROWTH_ALPHA` = 0.05) or their mean reaches log2(`NO_GROWTH_FACTOR`) (1.5). Both are settings; `None`
in the plumbing means "read the module constant when used", so tests can switch the rule off by
monkeypatching the constants. Tests that predate the rule do that through an autouse fixture and say so;
`TestNoGrowthRule` covers the rule itself. Pass the same two values to `output_meta` as to the derivation,
or `meta.no_growth` will misstate the rule. The paired test is not uniformly stronger than Welch: where
the ratios vary more across replicates than the raw values do, its p is larger (SMGDB00000013, Comamonas
in co-culture: Welch 0.02, paired 0.07).

## The name in running text

`brand.NAME_HTML` and `brand.in_prose` mark the name as a name wherever it stands in a sentence: the
wordmark's two parts a step lighter, applied by `gui._page` to every page body (Karoline, 2026-10-03:
"please use a special style for grownet, so sentences starting with it don't look strange"). `in_prose`
walks the markup and leaves `code`, `pre`, `title`, `script`, `style`, `textarea`, `option` and `a` alone,
so commands, paths, the document title and link labels stay plain; a link is colored already, and the
name's green inside one reads as a smudge. In the README the same job is done with bold, in prose only.
A test in `tests/test_help.py` pins both halves.

## Continuous culture and the metric

Chemostat and serial dilution experiments are derived when the metric is one that suits them, which today
is `max` alone (`derive.METRICS_FOR_CONTINUOUS_CULTURE`): the level such a culture settles at compares with
and without a partner, an area under the curve says how long the run was, and a growth rate is the dilution
rate (Karoline, 2026-10-03: "the no-chemostat filter is too harsh, we should allow it when max is the
growth property being compared"). Those arcs carry the caution `continuous_culture` and are shown; with
another metric they are left out unless `--include-non-batch` is given, and then they keep the `non_batch`
quality flag and stay hidden. The cultivation mode is part of `conditions`, so no comparison mixes modes.
Measured when it was built: no study in mGrowthDB has a non-batch pairwise or drop-out design (1, 5 and 11
are single large communities), so no current network changes.

## Missing numbers, and the sign column

A number the derivation did not compute is missing everywhere, never 0 and never a blank cell (Karoline,
2026-10-03): `null` in the neutral JSON, left out of GraphML and of the Cytoscape payload (with the column
declared, see below), and written as "not computed" on the page. A comparison with no ratio (obligate,
abolished) reads "no ratio" there. The result table's third column is "sign", since "direction" belongs to
the arc itself. Both are pinned in `tests/test_interface.py`, which quotes her.

## The three numbers of the test

`p_value` is Welch's raw value, `q_value` is that value corrected for multiple testing over every
comparison of one search, and `significance` is -log10 of the q-value (Karoline, 2026-10-03: "let's define
significance as -log10(q) and q-value as the multiple-testing-corrected p-value"). So p and q run one way,
smaller is stronger, and significance runs the other, larger is stronger, which is the one to map
continuously in Cytoscape. `derive.significance_of` caps it at `SIGNIFICANCE_CAP` (15), since -log10(0) is
infinite and Welch reports p = 0 when neither side varies and the means differ. The filter
(`--max-adjusted-p`, register item 31) acts on `q_value`, unchanged.

Before this, `significance` held the corrected p-value, which read backwards for anyone styling on it.
`effect_from_logratio` takes the q-value, not `significance`, for the same reason.

**Cytoscape turns a null number into 0.0**, and 0 is the strongest q-value there is, so an untested arc
would pass a "q below 0.05" filter inside Cytoscape. `cytoscape.network_json` leaves an empty number out
of the payload instead, which keeps the cell genuinely empty. A column only exists in Cytoscape once some
arc carries it, so `cytoscape._declare_columns` creates the ones an arc may lack
(`OPTIONAL_EDGE_COLUMNS`) after the network is posted: every arc then carries p_value, q_value and
significance, empty where there was no test (Karoline, 2026-10-03; checked against Cytoscape 3.10.3, where
a network of untested arcs had no such column before).

## The matrix, the growth rates and the gLV package (#108)

`grownet.matrix` turns a network into a square table and into the parameters a generalized Lotka-Volterra
simulator takes (register item 32, Karoline 2026-10-03). What a later agent needs to know:

- A cell holds the log2 mean as it is, not a fitted coefficient, and `A[i][j]` is the effect of j on i, so
  rows are affected and columns are the actor. The plain matrix (the format menu, `--format matrix`) has 0
  on the diagonal; only the gLV package sets -1, by convention, for self-limitation.
- One cell per ordered pair, so arcs of one pair merge across conditions and studies by their median,
  register item 14's rule, including its refusal to merge arcs of opposite sign: such a pair stays 0 and
  the package README names it. An obligate or abolished arc has no ratio, so it carries `matrix.EXTREME`
  with its sign, +10 or -10 (Karoline, 2026-10-03, after the first build left those cells at 0): a stated
  extreme, not a measurement. It never enters the median of the arcs that do have a ratio, and
  `matrix.by_convention` is the list the package README prints cell by cell. `matrix.counts` gives the page the arc-to-cell numbers, so a 6-arc
  search that makes 2 cells says so instead of looking like the hidden-arcs mismatch again.
- A reported growth rate (`derive.monoculture_rates`, `derive.merge_rates`, `derive.growth_rates`) is the
  maximum specific growth rate in monoculture by the chosen rate method, median over every monoculture
  replicate of every study, with each study's own median beside it. Batch monocultures only: in a
  continuous culture the rate is the dilution rate, and a co-culture rate is growth with a partner, which
  is the comparison itself. The rates ride in `meta.growth_rates` (with `without_a_rate`), so a downloaded
  network says what it was reported with.
- Rates are keyed by node id, which is a strain. `matrix.for_nodes` maps them onto the network's own nodes,
  so a genus-merged network takes the median of its strains' rates.
- The rates are read from the studies the search already read, with `wanted` set to the organisms of the
  derived arcs, so no rate costs an extra request to mGrowthDB.

## The R companion package (#110)

`r/` holds an R package called `grownet`, the other end of Send to R. What a later agent needs to know:

- **The wire format is `grownet.glv/v0`** (`matrix.glv_payload`), served at the page's `/glv.json` and
  posted by `rbridge.send` to the port the R package listens on (8793 by default). It holds the same
  numbers as the zip, the caveats as fields, and grownet's README text, so neither route loses what the
  other carries. Change the format id when the fields change; the R package warns on an id it does not
  know and reads it anyway.
- **The caveats are enforced in R, not explained**: `print` shows them every time, `glv_matrix` warns and
  names the cells holding the stated extreme (`placeholders = "na"` or `"zero"` converts them), and
  `as_miasim` stops when an organism has no growth rate. That was Karoline's answer to her own question
  about the README (register item 33).
- **The listener is base R sockets** (`serverSocket`, `socketAccept`), so installing the package pulls in
  only jsonlite. It answers one request and closes the port; a GET gets a line saying what the port is.
- **miaSim is suggested, never imported.** `as_miasim` returns the argument list for
  `miaSim::simulateGLV`, which solves dx/dt = x(b + Ax), the order the matrix is written in.
- **An unscaled matrix diverges**: on SMGDB00000004 the cells outweigh the -1 diagonal and deSolve returns
  NA. `glv_scale()` divides the off-diagonal by one factor; it is a modeling choice, so nothing applies
  it by itself, and the printout and both READMEs say so.
- **The install line carries `ref = "media-and-experiments"`** (`rbridge.R_BRANCH`) because `r/` is not on
  `main` yet; drop the ref from `rbridge.INSTALL_R` and from the three texts that quote it (the help page,
  the page hint, both READMEs) once it merges. A plain `install_github` on a public repository can still
  answer 404 when git has stored a token that cannot see it, which is what `rbridge.INSTALL_TROUBLE` says
  (Karoline hit both on 2026-10-04). It points at `install_local` from a clone and **never at clearing the
  token**: "it alters their system settings in ways that can affect them negatively" (Karoline, same day).
  A test in `tests/test_help.py` keeps the help page free of that advice.
- Checking the R side: `R CMD build r && R CMD check --no-manual grownet_0.1.0.tar.gz`, or `make r-check`.
  The tests live in `r/tests/testthat` and include a real POST into the listener.

## The second box: media, experiments or studies (#113)

`grownet.selection` parses the box and matches experiments; `derive.select_experiments` applies it.

- **Media are structured after all.** Every experiment carries `compartments[].mediumName` (559 of 559 on
  2026-10-04), so a medium is matched there first, and against the description and the experiment name as
  well, since what tells experiments of one study apart lives only there. The match is a case-insensitive
  substring because the spellings differ: Wilkins-Chalgren appears four ways, one misspelled "Anerobe".
- **An entry is an id by its shape** (`EMGDB\d+`, `SMGDB\d+`) and a medium otherwise. Study ids narrow
  which studies are read, the way the retired "Only these studies" setting did; media and experiment ids
  are applied per experiment inside the derivation.
- **Naming a comparison keeps its monocultures** (Karoline's choice): `select_experiments` adds the
  monoculture experiments under the same `conditions()` and reports them, since one id alone would give no
  arc. `_choose_monocultures` then picks among them as always.
- **Arcs carry `medium`** (`selection.medium_of`), in the model, the schema, GraphML, Cytoscape and the
  report. Merged arcs join the media of their parts.
- Selecting is not a method change: the medium is part of the conditions key, so comparisons never mixed
  media. Register item 8 carries this.
- `matrix.dropout_arcs(net)` counts the arcs a gLV package holds that may act through a third species;
  the README and the R printout say the count, or that there is none. Both gLV settings are ordinary
  advanced settings; the **gLV mode** button (`gui.glv_mode`, `gui.glv_mode_on`, `--glv-mode`) sets them
  together and says so, which is what Karoline asked for after two checkboxes in the bar read as "quite
  complex" (2026-10-04). It toggles: pressing it again restores both defaults, and it is drawn as a
  switch (`button.switch` with a track and a knob in `brand.CSS`), green when on and white when off, with
  `aria-pressed` for anyone who cannot see it. It stays a submit button, so the page keeps its no-JavaScript
  rule: the server re-renders the switch the other way.
- `matrix.media(net)` feeds the gLV README, the payload's caveats and the R printout: a package built from
  several media says so in capitals, because a simulation is of one environment. The All network spans six.

## Gotchas

- mGrowthDB serves growth curves, not interactions; interactions are derived.
- Study SMGDB00000008 (Gutierrez and Garrido 2019, mSystems, doi 10.1128/mSystems.00185-19) yields
  drop-out arcs only (#47). Per its methods, each deletion was a single bioreactor and only the full
  community ("All") ran in duplicate, so `DeltaAll_1` and `DeltaAll_2` are biological replicates while the
  two bioreplicates inside each mGrowthDB experiment are not independent cultures (the qPCR reactions were
  run in triplicate). The paper names the lack of replicates as a limitation. Its sd values are therefore
  technical spread. crossfeed does not correct source data; the fix belongs in mGrowthDB (Karoline).
  qPCR samples are at 0, 10, 20 and 30 h.
- mGrowthDB's structured conditions can miss a difference that only the free-text description records:
  in SMGDB00000004, `RI_BH +Ac` and `RI_BH -Ac` (with and without initial acetate) have identical
  compartment records. `crossfeed.derive.run_group` keeps them apart by their descriptions.
- Perturbations (substrate pulses, dilutions) can explain a jump in a curve. mGrowthDB records them only
  for chemostats so far (SMGDB00000005); a batch study with perturbations would need the spike guard to
  take them into account (Karoline, on #62).
- In the FP/BH study, monoculture and co-culture growth use different measurement techniques; edges carry
  a technique-mismatch flag. The magnitude is provisional, and near the neutral band the sign can move too
  under a cross-technique offset, so a mismatched edge's direction is not fully dependable either.
- The baseline keys nodes at genus and species (`_gs`), so strains of one species collapse to one node and
  the monoculture lookup keeps the last one seen. It now records that collision in `skipped` naming both
  strains, so the pick is visible, but it is still a pick: which strain to keep is METHOD_NOTES setting 7.
  Nodes carry no NCBI taxid yet, which is why a crossfeed network does not line up with a microbetag
  network in Cytoscape.
- One taxon id can appear under several names across studies: 411483 is "Faecalibacterium prausnitzii
  A2-165" in SMGDB00000004 and "Faecalibacterium duncaniae A2-165" in SMGDB00000005 and SMGDB00000011,
  after the 2022 reclassification. Names are not stable identity; taxon ids are (#23).
- Sign is encoded three ways in `gui/index.html` (color, dash, arrowhead), so anything else an edge needs
  to say has to use a different channel. Indirectness (`evidence` = `dropout`) uses an open ring at the
  edge midpoint. `edgeGeom` returns the path and that midpoint together so the two cannot drift apart;
  add to it rather than recomputing the curve anywhere else.
- Baseline edges are point estimates with no standard error, and edges for one interaction are never
  merged (each condition and study is its own edge), so an edge's `study_ids` has one entry today.
- The gate scans every tracked file, including this one: no dashes as punctuation, US spelling, no
  absolute local paths.
