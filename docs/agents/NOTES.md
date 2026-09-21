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

## Open questions (need a human)

- Method and format questions are collected in "Open decisions" in
  [docs/METHOD_NOTES.md](../METHOD_NOTES.md).
- Where each mGrowthDB study's license is published; the study endpoint does not expose it, so
  `study_license` is marked unresolved.

## Gotchas

- mGrowthDB serves growth curves, not interactions; interactions are derived.
- Study SMGDB00000008 (Gutierrez and Garrido 2019, mSystems, doi 10.1128/mSystems.00185-19) yields
  drop-out arcs only (#47). Per its methods, each deletion was a single bioreactor and only the full
  community ("All") ran in duplicate, so `DeltaAll_1` and `DeltaAll_2` are biological replicates while the
  two bioreplicates inside each mGrowthDB experiment are not independent cultures (the qPCR reactions were
  run in triplicate). The paper names the lack of replicates as a limitation. Its sd values are therefore
  technical spread. qPCR samples are at 0, 10, 20 and 30 h.
- mGrowthDB's structured conditions can miss a difference that only the free-text description records:
  in SMGDB00000004, `RI_BH +Ac` and `RI_BH -Ac` (with and without initial acetate) have identical
  compartment records. `crossfeed.derive.run_group` keeps them apart by their descriptions.
- The spike guard (max/median above 100) also fires on a declining curve whose maximum is the inoculum at
  0 h, which is not a spike (SMGDB00000013, Microbacterium and Ochrobactrum monocultures).
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
