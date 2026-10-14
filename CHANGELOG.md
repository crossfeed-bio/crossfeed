# Changelog

All notable changes to grownet (called crossfeed before 0.1.0) are recorded here. The format follows Keep
a Changelog. A released version is a promise about content: a tagged version is never reused for changed
content.

## [Unreleased]

### Upgrading

- **The gLV payload moves to `grownet.glv/v2`** (Karoline, 2026-10-14: "follow your recommendation for
  Q4"). It adds `caveats.arcs_left_out`, `caveats.cell_media`, `caveats.dropout_arcs_in_cells` and each
  matrix's `cells_with_unrecorded_medium`, and `matrices[].media` now names the media of the cells a
  matrix holds, where it named those of every arc between its organisms (or the network's), so a reader
  of v1 would have read the new `media` as the old one. The R package of this version reads v2, v1 and
  v0; an older one reads v2 with a warning that it does not know the format.
- **The format id moves to `grownet.interaction_network/v4`** (Karoline, 2026-10-12, #266), for five
  optional fields a reader could not get from a `/v3` file. On an arc: `metric_unit`, the unit of
  `metric_with` and `metric_without` (#214); `window` and `window_unit`, the interval the metric was
  computed over, which an area depends on (#213); and `vs_other_removals`, a drop-out arc's strength minus
  the median of the other drop-out arcs measured against the same full community (#209 option 2). On a
  node: `taxon_id_refused`, why its `taxon_id` is not its identity, where mGrowthDB gave one id to
  different strains of a study (#217 option b). Nothing a `/v3` field means changes, and `/v3` files still
  read and validate. Live: study 8's arcs were measured over 30 h (100 arcs) and 20 h (15), which nothing
  said before.
- **The daily All network is published in both formats** (Karoline, 2026-10-12, #289: "Publish both"). A
  copy fetches the file named by its own format id, `all_result.v4.json` from this version on, so a format
  move never strands an installed copy again; and `all_result.json` keeps being written for installed
  0.3.x and 0.4.x copies as the same network in `/v3`, the added fields removed. Checked with the released
  0.4.0 from PyPI: it serves the `/v3` file (145 arcs) and refuses the `/v4` one, as it should.
  **Installed 0.3.x copies** also fetch `all_result.json`, and 0.3.0 checks neither the derivation nor
  anything but the format, with `integrated` as its default: since 2026-10-10 such a copy has been served
  the comparison's network as its All at that default. The file cannot tell 0.3.x from 0.4.x apart, so the
  answer is to upgrade.

### Added

- **A study whose growth rates are slow as a block is named** (Karoline, 2026-10-12, #173: Craig's
  agent's study-level tripwire, as a flag, "Keep 5x"). When every rate from one study is more than 5 times
  slower than the median of the other studies' own medians in the run, the report says so, and
  `meta.growth_rates.slow_studies` carries it. Nothing is refused: slow can be the organisms or the study's
  conditions. On all of mGrowthDB today it names SMGDB00000013 at the defaults (6.6 times), which is the
  sole source of the published rates of *A. tumefaciens* and *C. testosteroni* MWF001, and nothing in gLV
  mode.
- **A check that reads the live corpus** (#237). Every other check was closed over the repository: the
  gate reads source, the suite is offline, the release check compares strings. After each daily publish,
  `packaging/live_check.py` checks the All network just derived from mGrowthDB, and one study derived in
  gLV mode, for properties rather than numbers, so it does not go stale as mGrowthDB grows: the fields
  each kind of arc promises, the arithmetic between them under the derivation that made them, the schema
  with no undeclared key, and nothing empty. A violation opens its own `live-check-failed` issue. On
  2026-10-12 every property held on 145 arcs, 78 below the threshold, and the gLV-mode study.
- **The adjacency matrix CSV travels with a description of itself** (Karoline, 2026-10-12, #212: a
  sidecar file). `--format matrix --out x.csv` writes `x.about.txt` beside it, and the page's format menu
  has "Adjacency matrix: what it is (TXT)". It holds the version, date, derivation and metric, every
  setting, which way the rows run, what `0` and `NA` mean, the pairs left at 0 for disagreeing in sign
  (which the CSV dropped without a word), the `NA` cells with their bounds, the media and the sources.
  The grid itself is unchanged, so a plain `read.csv` still reads it.
- **The report names what no drop-out arc shows on its own** (#207, #209). It lists every ordered pair
  measured both as a pair and inside a community with **opposite effects**, both arcs together, as a
  result: in Karoline's words, it "just shows that higher order interactions matter". On the All network
  that is *Roseburia intestinalis* on *Blautia hydrogenotrophica*, an inhibition from the biculture and a
  facilitation from the drop-out. And it lists the **drop-out arcs that share one full-community
  reference**, by target: part of each such arc is how the target fared in that community rather than what
  removing the member did. On the All network that is 118 arcs in 17 groups. The `provisional` sentence
  says the second limit, and `docs/LIMITATIONS.md` gains entry 8. Nothing is merged, re-centred or
  withheld. Option 2 of #209, each drop-out arc against the other removals of its target, is published as
  `vs_other_removals` (under Upgrading); option 3, making that the comparison, was not taken.

### Changed

- **A monoculture measured only as a whole culture gives its growth rate and lag from a count** (Karoline,
  #140: option 1 on 2026-10-07, "Counts only" on 2026-10-12): a plate count or flow cytometry, never optical
  density, and never a carrying capacity. The rate says where it came from (`rate_sources`, and in the
  report). Such monocultures were dropped replicate by replicate. Measured on SMGDB00000009 through
  `derive.growth_rates`, *E. coli* LF82 and *B. fragilis* NCTC 9343 get a rate from flow cytometry. No
  command shows those two today: a rate is reported for the organisms of a network, and study 9 holds
  monocultures alone.
- **A growth rate is not pooled across monocultures that started more than 10 times apart** (Karoline,
  2026-10-12, #81 b), measured at each curve's first time point. The study's rates for that organism are
  left out and named. Live: *A. tumefaciens* (24 times) and *C. testosteroni* (101 times) in
  SMGDB00000014, so the All network's rates for both now come from SMGDB00000013 alone, and the run's
  notes say why. Measured through `derive.growth_rates` over every study, *S. putrefaciens* in
  SMGDB00000018 (85 times) is refused too, which no command shows today, since study 18 derives no arcs.


- **In gLV mode an organism's published growth rate and carrying capacity no longer move with a display
  setting** (Karoline, 2026-10-12, #204: the rate is a property of the organism). They were a median over
  the arcs that survived the absence threshold, the q-value filter and the low-quality filter, so
  `--include-absent` moved one rate by 14 per cent. They are now a median over every row the derivation
  fitted. On all of mGrowthDB at the defaults this moves two published rates, *B. thetaiotaomicron* 0.7915
  to 0.7848 /h and *R. intestinalis* 0.5899 to 0.5806 /h, with their capacities, and gives *C.
  testosteroni* the rate it was fitted with; with the flag or the q-value filter the numbers are now
  identical.

- **The daily All network is served while it is less than 36 hours old**, not one day (Karoline,
  2026-10-12, #196). GitHub starts the daily run late by a varying amount: the gap between two published
  artifacts reached 27h20m and 7 of 12 gaps exceeded a day, so the file went stale most nights before its
  replacement landed and every copy of grownet derived All live from mGrowthDB at the same time. Still one
  run a day. The format id and the derivation check, which keep a reader from a wrong artifact, are
  unchanged.

### Fixed

- **A read that fails while the growth rates are read now marks the run incomplete** (#247's gap): the file
  was marked complete before that stage ran, so the run exited 0 and an organism whose monocultures could
  not be read looked as if it had no measurable rate.
- **A merged arc says nothing one member said alone.** `--merge-genera` and `--merge-arcs` gave a merged
  arc its first member's `window`, `metric_unit`, `metric_with`, `metric_without` and `vs_other_removals`;
  these are now kept only where every member agrees, and `vs_other_removals` is never set on a merged arc.
- **The gLV payload's `carrying_capacity_curves` counts curves**, as `growth_rates.csv` does, not fitted rows
  (the slip #259 fixed for `replicates`), and is empty where there is no capacity, where it sent 0.
- **The matrix sidecar says "at most" for an abolished arc's bound**, which is an upper bound; it said "at
  least". It also says when the run was incomplete, which within-genus arcs have no cell, and how to read
  the CSV in R with its names intact; GraphML carries `complete`, `errors` and the build commit.
- **One organism, one name**: the arcs below the threshold and gLV mode's fitted rates now carry the current
  name, as the network does, and `--merge-genera` groups and lists a renamed strain, its arcs and its
  growth rate, by it (#24). The report's
  pairs the data did not support and its notes on the data read name organisms as their study does, and
  say so.
- **A merged obligate or abolished arc counts in the gLV package's sign check again.** Merged members
  whose bounds differ kept their shared rule without its bound, which read as "the rule bounds nothing",
  and the arc dropped out: beside an opposite arc the cell held that arc's number where it is a sign
  conflict left at 0, and alone it wrote a 0 named nowhere. Every arc's direction now counts, converted or
  not, as it does in the adjacency matrix; a merged arc with no median ratio says so.
- **The gLV package says where each left-out effect is**: an effect on or by an organism in no matrix, or
  between two organisms in different matrices, is listed as in no matrix, not as left at 0, once with all
  its reasons; a pair whose arcs disagree in sign is named there too when its organisms share no matrix,
  where it was named nowhere; arcs left out of a cell that still holds a value are listed apart, among
  them an arc that gives no number beside arcs that do, which was dropped without a word, while arcs
  beside a cell of 0 are listed with that cell; and the unit sentence counts the effects between
  organisms counted differently that were measured, where it said none ever was. A matrix an organism
  left for an unusable self-limitation counts only the cells, media and sign conflicts it still holds,
  and that organism's effects are in no matrix, not also left at 0. A cell names only the media of the
  arcs in it; the lists of cells from the ratio, from merged arcs or from a comparison where one side did
  not grow hold only cells a matrix holds, each labeled only by the arcs in it; and the warning about
  several media (README and R, from the payload's new `cell_media`) is about the media of the effects
  between organisms, matrix by matrix since a simulation takes one matrix: a matrix whose effects come
  from several media is warned about, matrices of one medium each are named so, cells with an arc that
  records no medium are named and not taken for a second medium (each matrix's
  `cells_with_unrecorded_medium` in the payload), a package whose matrices hold no effect says so, and
  the media of arcs in no cell are named apart. The drop-out count is of the arcs in the cells
  (`dropout_arcs_in_cells`), with the network's others named apart. The steady-state check matches a matrix by the media of its cells, or, holding none, of the arcs between
  its organisms.
  The report prints several entries of the second box on its one line, joined with "; " there, in its
  query line and in the page heading since a medium's name can hold a comma, and says a derivation without
  the no-growth rule did not apply it, where it printed a count of nothing. The steady-state check says
  it did not run when no organism has a taxon id to look chemostats up by (a genus package) or the
  search failed or no study it named could be read, where it said mGrowthDB holds no continuous culture
  of them, and names the studies it could not read; a matrix with a cell recording no medium is scored
  with a note saying so. At alpha 0 the report says the test is off and, while a comparison whose set's
  metric was not positive is still censored, that its bound uses the factor; the factor is marked unread
  only when none is, and the page and report say this run did not read it, not the derivation. The
  command line names how many studies could not be read, and `--to-r` carries the steady-state check
  to R as the zip and the page do. An untouched page form leaves the no-growth rule at its default,
  where every search said it was changed and recorded 0.05 and 1.5. A merged arc whose members do not
  all record a medium says how many do not, and the gLV package counts its cell as such. The model assumption no longer says every cell was measured between two organisms.
  R reads `pairs_left_out`, `across_units` and `arcs_left_out` with their actors and prints them.
- **A merged arc keeps no single comparison's bound, capacity, coefficient or fit**: every such field is kept
  only where all merged arcs agree, a merged arc's coefficient is the median of its members', and in a gLV
  package its cell is labeled as a merged arc's, not as one from a network saved before the rates were
  recorded. gLV mode with `--merge-genera` reports the fitted rates on the genus nodes, where it said none
  could be computed, and arcs from an organism to itself are counted as arcs. A genus row in
  `growth_rates.csv` counts its strains' replicates and plateau curves and says where its capacity came
  from; a genus of one strain is that strain's row. It counted fitted rows and left the provenance empty.
  A genus row of several strains also keeps the lag's method, the plateau's fall, media and other media,
  and sends its replicates in the gLV payload, where it sent null beside the zip's count. The report and
  the rule and the gLV package README say its rate and capacity are the median of its strains' own, and
  the report names those strains and the counts the medians rest on; "median of 7 monoculture replicate(s)" named a median
  that was not taken. A genus with no capacity names no medium for one, and the report, the README and
  the payload say when its strains' plateaus are in units that are not converted, with every such plateau
  counted as left out. Every curve or fitted row another medium holds is counted as left out, where one
  entry per medium was counted as one, and so is every plateau another study measured in another
  abundance unit, which was in no count. A left-out fitted row is named by its experimental condition.
  A study with plateaus and no rate no longer decides an organism's rate unit (the first study read did,
  and every later study's rates and the organism were dropped in that order); a study or fitted row whose
  rates are in another time unit keeps its plateaus, in both derivations, and the report names the rates
  left out. A genus whose strains' rates are in different time units has no rate, where the median was
  taken across them, and the report, the README and `meta.growth_rates.why_without_a_rate` say why; so
  does an organism whose every study's rates were left out for their starting spread (#81), which the page
  said had no monoculture read or no rate from its curves (SMGDB00000014's two organisms), and a genus of
  such strains, naming them. The gLV package carries that reason beside "grows only with a partner", so
  R reads it, and R's print says `as_miasim()` stops only for an organism inside a matrix.
- **`derive <study>` says it names organisms as that study does** (its help): the current name of #24 needs
  the whole corpus read, which a species search and `--all` do and a single study does not, so the same
  taxon can read "F. prausnitzii A2-165" there and "F. duncaniae A2-165" in a search.
- **`derive <study> --merge-genera --report-rates` computes the genus rates** (in the default derivation):
  it asked for the monocultures of the genus nodes, which no monoculture is, and said no growth rate could
  be computed for any organism. This predates 0.4.0. A
  capacity in gLV mode reports the stage size and source of the rows it is taken from.
- **A rate from a culture-level count says so** in `capacity_source`, so `growth_rates.csv`, the gLV payload
  and the report name it, without a new field; a rate that also rests on per-strain curves does not blame
  the count for its missing capacity.
- **The daily artifact's `/v3` copy carries only meta keys 0.4.0 declares**, so an installed 0.4.0 does not
  call it suspect; a copy is written for EVERY older format from `/v3` on, read from the manifest, so the
  next format move strands no installed copy either.
- **`grownet validate` reads a daily artifact** (`all_result.v4.json`) by validating the networks it carries,
  where it said "INVALID: schema is None" about a good file, and says so when an artifact carries none.
- **In gLV mode, `replicates` and `capacity_curves` count every monoculture set behind a rate or a
  capacity**, one per study and condition matched, where the largest set alone was counted: SMGDB00000007's
  organisms rest on 6 monoculture replicates, not 3, and Comamonas in SMGDB00000014 on 9.
- **The live check's tolerance for `effect_over_sd` is the exact rounding bound** (Craig's agent on #281,
  correcting the first-order one it had given): honest rounding reached past the old bound at every sd,
  by 2x at sd 1e-4. It is applied to every arc with an sd above the rounding, and the check says on how
  many arcs it was loose (the bound above a tenth of the value) or could not run (none in today's All
  network). `packaging/compare_growthrates.py` makes the counts `grownet.rates` states against R's
  `growthrates`, on a selection of curves it states.
- **The live check reads every network in each older-format file**, the arcs below the threshold as well
  as the network, which 0.4.0 reads too, and checks that each file would be served by the copies that read
  it: its result format, its time and its derivation. An older-format file is written only in the result
  format and with the derivation its readers accept (0.4.0's defaults ask for replicate).
- **The live check tells "could not run" from "a property broke"**, by exit code (2 against 1) and in the
  issue it opens; the build-failure issue opens only when the publish step did not complete, and says
  some files may already have been replaced.
- **The release check refuses an empty version section**, entries left under [Unreleased] at a tag, and a
  help-page release date that differs from the changelog's; RELEASING.md's checklist, emergency procedure (pause the workflow first) and its
  statements about which copies read which file for how long now match what is true.
- **The R listener's test runs in CI.** It is a `skip_on_cran()` test and nothing set `NOT_CRAN`, so it was
  skipped since #120 while failing on the example's changed matrix; CI and `make r-check` set it now, and
  fail unless the R tests report `SKIP 0`.
- **A Baranyi start that ran off to an enormous rate raised `OverflowError`** instead of being rejected
  like any other unconverged start. First met on optical densities while building the above.

- **A strain is shown by its current strain name, not the bare species**, where mGrowthDB's most recent
  study names only the species (Karoline, 2026-10-12, #24). The current name is now the latest name
  mGrowthDB gives under that species with a strain designation: taxon 411483 is "Faecalibacterium
  duncaniae A2-165" rather than "Faecalibacterium duncaniae", and 74426 "Collinsella aerofaciens RCC
  1377". 2 of mGrowthDB's 63 taxa change. Only names the database itself uses are shown.
- **All says why it was derived live, when the network derived once a day was not used** (#157): the
  file was too old, from another format, derived another way, unreachable, or, worth reporting, fetched
  and unreadable, which is a defect in grownet. All five used to look the same, and a defect in reading
  the file was indistinguishable from a stale one.
- **A search's notes reach the report and the command line**, not only the page: a value in Exclude
  these studies that excluded nothing, a check asked for and not run, and the reason above.
- **The page's report says what its search read and reused from mGrowthDB**, as the command line's has
  since #182: it printed no `reads:` line at all. The counts are this search's own. The page keeps one
  connection for an hour, so the command line's way of reading the totals would have reported every
  earlier search as this one's. When another search ran at the same time, the report says the two cannot
  be told apart rather than printing a mixed count. And it counts the responses the client answered
  from memory, which nothing counted: run live, a second search over the same studies said "0 from
  mGrowthDB, 0 reused" about a network built from 429 responses (#187).
- **A growth curve whose steepest window rises can no longer return a negative "maximum growth rate"**
  (Karoline, 2026-10-12, #229). The refit over growthrates' first-to-last span can fall below zero when two
  rises are separated by a deep fall, and a non-positive rate read downstream as no growth. Such a curve
  now has no rate, with the reason, and its replicate is left out as any unreadable rate is, where
  growthrates returns the negative number: one of the three places grownet departs from growthrates, which
  `grownet.rates` names and `packaging/compare_growthrates.py` counts. On all of mGrowthDB it is 2 of 1090
  strain curves (a hand count), both in SMGDB00000005's chemostats, which the default leaves out; one of
  the two also holds a value <= 0, which growthrates refuses first.
- **The growth-rate docstring says what `easylinear` does** (#229). It said the refit spans "every window
  whose slope reaches" the quota; it spans from the first such window to the end of the last, every
  window between included, which is what `growthrates`' `fit_easylinear` does. Kept as it is (Karoline,
  2026-10-12: option 2): checked against `growthrates` 0.8.5 on studies 4 and 5, the two agree to 5e-15
  on all 342 curves both fit. No number changes.
- **The gLV package's files describe themselves correctly** (#210, #211):
  - the zip's README says to match `growth_rates.csv` to a matrix **by the organism column, never by
    position**: each matrix holds its own unit's organisms in its own order, and a positional read gave a
    plausible, wrong simulation, off by factors of 2 to 4;
  - in gLV mode the README no longer describes the off-diagonals with the comparison's formula, nineteen
    lines after its own integrated description, nor says a setting chooses the estimator that the
    integrated form does not read;
  - cells "from a comparison where one side did not grow" are named only where they are in a matrix;
  - `capacity_curves_left_out` writes a count of 0 as `0`, not as a blank that R reads as `NA`;
  - a nonzero value below 5e-5 is no longer printed as `0`, which means no interaction; it is written
    in scientific notation instead (`3e-05`), which `read.csv` reads, and every other number prints as before;
  - in R, the coverage line counts organisms outside every matrix (it read "8 of 8" for an 11-organism
    network), `summary()` gains `network_organisms`, and `glv_write()` writes the three rate columns it
    was missing and the matrices at four significant digits, as the download does.
- **A run that could not read everything now says so in the file it writes.** A study that answered 404
  was written into `meta.studies` (which the schema describes as the studies the search READ), the file
  carried no trace of the failure, and `grownet validate` passed it. Now `meta.studies` lists only the
  studies read, `meta.errors` names what failed, `meta.complete` is false, and `validate` notes the file
  as incomplete. The report reads the errors from the file. And `derive <study> --live` exits 1 when
  curves could not be read, as the species and All paths have since #243 (#247).
- **0.4.0 called its own output suspect.** `grownet validate` on a network 0.4.0 derived said `meta has
  'project', which this version of the format does not declare`, and the same for `settings_not_used`:
  both keys were added in 0.4.0 and never declared in the schema. A third, `slice`, written by
  `grownet.slices.fp_bh`, had been undeclared since that module existed (found by Craig's agent on #274).
  All three are declared now. The data was right and the files were valid; only the note was wrong, and
  the format id does not move, since `meta` is an open object. The test behind it now walks the syntax
  tree for every form a key can reach a network's `meta` by, where it read one form and saw 2 of the 20
  keys (#274).
- **The daily All artifact's release description is rewritten by every run** and says what that run
  produced: studies, organisms, arcs, when, by which version and which derivation. It was written once, on
  the first run, so editing it in the workflow changed nothing, and it promised "the default settings" for
  `all_network.json` and `all_report.txt`, which nothing checks against a reader's version. It now says so,
  and which file the freshness rule governs (#236).
- **A collapsed All derivation is no longer published.** A run with no arcs is refused, and so is one with
  less than half the arcs of the artifact it replaces unless it is run by hand with `allow_drop`. The
  workflow refused only a run with errors, so zero arcs published and was served to every reader at the
  defaults until the next run (#236).
- **`packaging/check_release.py` refuses a tag that already names another commit**, and with no tag reports
  a tagged version as released rather than ready. It said `v0.3.0 is ready` on a tree whose v0.3.0 was
  tagged and on PyPI (#236).

## [0.4.0] (2026-10-11)

**Read this before upgrading: the numbers change.** A version is a promise about content, so this says
what moved rather than leaving a reader to find out by diffing. **This is a minor version and not a
patch, because the default derivation changed**: a reader who upgrades and re-derives gets a different
network from the same database, which is not what a patch number promises. Two days of post-release
review, 104 entries below, and three of them change what a derived network holds:

- **the default derivation is the specified comparison again** (first entry under Upgrading). **Every
  network derived without gLV mode changes, and almost all of them grow:** on the whole of mGrowthDB the
  default goes from **12 arcs to 145**, over 24 organisms instead of 9. This is the largest change here.
- **the rate table is keyed by the matched monoculture set** (#255 item 2), which moves `se`, `sd`,
  `p_value` and `effect_over_sd` under the integrated form. Measured corpus-wide in gLV mode: 4 of 16
  p-values move, **one crosses 0.05** (`0.04753` to `0.05386`), and **two arcs fall below the absence
  threshold**, so a gLV network of 12 present arcs becomes 10.
- **the spike limit now applies under the integrated form** (#255 item 1). At the default factor of 100
  the corpus is byte-identical, so nothing changes unless a reader sets the setting; set to 1.5 on
  SMGDB00000014 it goes from 4 arcs to 1, where before it did nothing at all.

Nothing else here changes a number: the rest corrects what the tool SAYS about what it did, which is
most of the 104 entries, or fixes a guard that was claimed and not applied.

**A re-derive is the way to upgrade.** A network derived with 0.3.0 and a network derived with this
version are different measurements of the same database, and `meta.settings` plus `meta.tool_version`
in each file say which is which. **The format id does not move**: it is still
`grownet.interaction_network/v3`, because no field was added, removed or given a new meaning, so a reader
that already parses 0.3.0's files parses these without a change.

### Upgrading
- **The default derivation is the specified comparison again, and gLV mode selects the integrated form**
  (Karoline, 2026-10-10: "the default one, when we don't want to do simulations, should be the lenient
  one that allows for drop-out communities... In all our discussions, I always thought that we were
  comparing derivers only for the gLV mode"). **Every network a reader derives without gLV mode changes,
  and almost all of them grow.** On the whole of mGrowthDB the default goes from **12 arcs to 145**, of
  which **122 are drop-out arcs**, over 24 organisms instead of 9, with **15 censored arcs, 12 of them
  carrying a measured bound**, where there were none of either.

  The reason is not that one form is better. Each answers a different question and **neither is the
  stricter version of the other**, which is now written down for both. The integrated form derives no arc
  from a community of three or more, which Craig declined on #127, so no drop-out arc can exist under it,
  and it has no no-growth rule, so no censored arc, no measured bound and no `NA` cell. The comparison's
  own weakness is the one that made the integrated form the default in 0.3.0, and it is unchanged and
  still decisive **for a coefficient**: a coefficient from the comparison is a difference of two
  separately fitted rates divided by one partner mean, carrying the organism's own density as a confound.
  So a gLV package is still built by the integrated form, and gLV mode now switches the derivation as
  well as the three settings it already switched.

  **What changed is which evidence was weighed.** The comparison that chose the 0.3.0 default records its
  own command, `derive SMGDB00000007 --live --glv-mode --derivation <either> --steady-check`, and
  `--glv-mode` turns drop-out communities off on **both** sides, so it measured the two forms on the
  question gLV mode asks. The coverage cost it weighed, 30 arcs against 23, is a gLV-mode number; outside
  gLV mode the same trade is 145 against 12.

  **To keep 0.3.0's behavior**, pass `--derivation integrated`, or press gLV mode on the page. Arcs from
  the comparison carry no `se_rate_selection` and no `rate_unchecked` caution, which are the integrated
  form's machinery; they carry `se`, `sd`, `p_value`, `q_value` and `effect_over_sd` from Welch's t-test
  as they always have.

### Fixed
- **The spike limit did nothing at all under the integrated form** (#255 item 1, Karoline's decision of
  2026-10-11: "I'd go for your first option: apply it in `IntegratedDeriver.derive` after
  `replicates_for_experiment`, dropping each spiked curve per species and reporting it with
  `interaction._spike_reason` so the wording is the one the help promises"). That path read the setting
  and passed it to `replicates_for_experiment`, which attaches a NOTE to the replicate and never drops the
  curve; the exclusion lives in `interaction._unspiked`, which the path never called, and
  `Replicate.notes` was never read there. So `--spike-factor 1.5` removed 33 curves and named every one
  under the comparison, and removed nothing and named nothing under the form gLV mode selects, while
  `meta.settings.spike_factor` recorded 1.5 as that run's provenance. Measured live on SMGDB00000014:
  `--spike-factor 1.5` now goes from 4 arcs to 1 with 54 mentions in the report, where before both
  settings gave the same 4 arcs and no mention. **At the default factor the whole corpus is
  byte-identical**, so no published network changes; the setting stops being inert. The reason is the
  promised one, with its tail corrected where this form needs every member of a row together, so a
  replicate is left out of the experiment rather than of one species.
- **`target_capacity`, `partner_abundances` and the measured plateau were spike-blind** (#255 item 3),
  where the monoculture plateau path refuses the same curve in its own words. Both numbers are
  load-bearing: the first fits the self-limitation of an organism with no monoculture capacity, the second
  is the `x_j` a gLV coefficient divides by, and a spike is by construction a huge interior maximum, which
  is what a plateau reads. Measured: the guard changes the **number** for `partner_abundances`, and for
  `target_capacity` it usually changes the **reason**, from "the curve ends at 1/610 of its peak" to
  "implausible spike", because a spike that becomes the maximum left the curve ending far below it and the
  decline limit already refused it while naming the wrong cause. `integrated._measured_plateau` also
  refused every curve with a bare `continue` and recorded no reason at all, although the capacity help
  promises each is named with the others that gave none; it names all of them now.
- **The rate table was keyed by the fit and rebuilt from the surviving arcs, so `se_rate_selection`
  rested on a spread 4.96 times too small and two arcs said how many monoculture sets were matched and
  were wrong** (#255 item 2). `_widen_by_rate_selection` rebuilt the table from `pending`, which holds
  only the arcs that became records, keyed by `id(got)`: a fit whose arcs were dropped earlier (no
  coefficient, a unit mismatch, the R2-about-zero gate) was invisible although it ran in the same pass,
  and two co-cultures resolving to the same monoculture set counted twice. The spread is "how much
  stage 1 moves when the matched condition moves", so the matched SET is the unit and a dropped arc does
  not unmeasure its organism's rate. It is collected now where the fits are made, keyed by the set's own
  experiments.
  **This is not a change to the method**, which already says the figure is the spread of an organism's
  matched monoculture rates: the table computed that spread over the wrong set (Craig's agent on #255,
  2026-10-11, and his test for it, that the definition of the quantity does not move and only which data
  reaches it does).
  **Measured live on SMGDB00000014, the issue's own reproduction.** The spread goes from `0.0256` to
  `0.1267`, the factor of 4.96 the issue computed; the notes go from "matched to 3 different monoculture
  set(s)" to 5, with all five rates; and the arc that published "this organism has one matched
  monoculture set in this study" for an organism matched to five no longer carries `rate_unchecked`.
  **Corpus-wide, under gLV mode: 4 of 16 arcs' p-values move, one crosses 0.05 (`0.04753` to `0.05386`),
  two arcs fall below the absence threshold (12 present to 10), and `rate_unchecked` goes from 7 arcs to
  6.** Arcs change, so this is not a silent patch on a tagged release.
  `_flag_unchecked_rates` also stopped asserting one cause for every arc it reaches: it reaches an arc
  whose organism had several sets that all fitted the same rate, and one whose third component could not
  be computed, and for those the sentence was false. The caution is the same in all three, because what
  it says is that the assumption is unchecked; the note now says which of the three it is.
- **The gate now catches a definition written twice**, which is the failure a merge leaves that nothing
  else catches. Resolving thirteen branches on 2026-10-11, a keep-both-sides resolution gave one dict two
  `"outcome"` keys: Python silently keeps the last, so one branch's wording was lost, and the file parsed,
  every test passed and the gate was clean. The same shape took two test functions out of a file in the
  same session, and a test that no longer exists cannot fail. The check covers duplicate keys in a Python
  dict literal, duplicate top-level `def` and `class` names, and duplicate keys in a JSON object, which
  Craig's agent added to the technique and ran over the merged tree before this existed. Reported as a
  problem rather than a note, because there is no reading under which a shadowed definition is intended.
  `TEXT_EXT` is removed with it: nothing had read it since scanning became content-based, and a dead list
  of nine extensions at the top of the file #227 was about reads as load-bearing (Craig's agent).
- **The GraphML carried no schema id, no source and no citation** (#216), and it is the file a Cytoscape
  user shares. The schema id is the part that matters: `model.py` calls it the project's one guarantee,
  "the one signal that says the meaning of a field moved", and `significance` was the corrected p-value in
  `/v0` and is -log10(q) in `/v3`, which runs the other way, so a `/v0` and a `/v3` GraphML had identical
  column names, inverted `significance`, and nothing in either file to tell them apart. It now carries
  `schema` (the DOCUMENT's own id, so a network loaded from a `/v0` file says `/v0`), `schema_url`,
  `source_db`, `studies` with whatever each has to cite by, `project_url`, and one line saying what the
  display columns are and that the width of an arc with no measured strength is absolute. The viewer
  writes all of them too, and two tests hold the two writers together: the existing byte-for-byte parity,
  and a new one that compares the three shared constants by name so a drift says which one moved.
- **A network pointed at documents it gave no way to find** (#218 item 1). `meta.provisional` ends "see
  docs/METHOD_NOTES.md and docs/LIMITATIONS.md in the grownet repository" and the only URLs in a network
  were the study DOIs and the mGrowthDB API: the string `github` appeared nowhere, and `schema` is a bare
  id rather than a URL. `meta.project` now carries the repository, the schema URL and a URL for each of
  those two documents.
- **`--include-absent` was silently ignored by `--format matrix`** (#218 item 2). That format's own
  convention is that an empty or absent cell is 0, so an arc below the threshold has no cell to be kept
  in, and the matrix records no settings either, so nothing said the flag was asked for and dropped. It
  says so now, with the count, and the suggestion one step upstream is format-aware rather than sending a
  reader to a flag that does nothing there.
- **The published All artifact had no retrievable identity** (#218 item 3). The workflow replaces one
  file on a fixed release with `--clobber`, outside git history, so the file a reader downloaded is gone
  the next day and `derived_at` was its only identifier: a reader asked which version they used had no
  answer, and a re-derive gives a different network from a database that has moved on. The payload now
  carries `identity` with a `content_sha256` over everything except that block, so a reader reproduces it
  from the file alone by the recipe the block states, plus the run and the commit from the environment
  GitHub Actions already provides, which needs no change to the workflow and leaves a local run carrying
  neither rather than inventing them.
- **`license` was empty on every study, everywhere** (#218 item 4). mGrowthDB's study record has no
  license field at all, measured live: its keys are description, experiments, id, name, projectId,
  publishedAt, uploadedAt and url. The integrated path read a `license` key that never exists, which
  reads as "we looked and it was empty", and the report and the attribution block rendered it as
  "license: see study", sending a reader to look for something the source does not publish. They now say
  no license is stated by mGrowthDB and point at the study.
- **The `--fixture` route accepted every setting and applied none of them, in silence** (#222 item 1),
  which is the route a downstream implementer and this project's own examples use. Measured rather than
  reasoned, with a fixture built so each setting had something to act on: the same pair from two studies
  for merging, a q-value of 0.40 for the filter, a tiny effect with a spread for the threshold, a
  `single_replicate` arc for the quality filter. **All fourteen left the arcs byte-identical.** The
  mechanism is that `output_meta` runs only on the live path, so this route has no output stage at all:
  no absence threshold, no merging, no q-value filter. A setting that cannot apply is refused now, naming
  it, as `--deriver` already was. The report also printed a literal `(k = )` and an empty `settings:`
  heading, which said a run had no settings where the truth is that this route records none because it
  applies none; both now say that.
- **`validate` could not see a self arc or a `significance` that contradicts its own `q_value`** (#222
  items 2 and 3). A records file with one careless copy-paste gave a document whose JSON held 2 arcs and
  whose matrix held 1, and `validate` called it fine: an arc from an organism to itself takes no cell of
  its own, because the matrix writes the diagonal at that position. It is a **note** and not a problem,
  because `--merge-genera` produces within-genus arcs by design. And a file written to the pre-`/v1`
  convention, where `significance` held the q-value rather than -log10 of it, validated cleanly while
  reading as a far weaker result than its own `q_value` states; that cross-check is applied only to the
  format ids where the relation holds, and only as a note, since a reader may have rounded. Checked
  against grownet's own output: 206 of the corpus's 223 arcs carry both fields and none is flagged.
- **The published All artifact dropped four parts of the result its own module says it holds** (#228).
  `published.py` describes the file as holding "the whole result of the search, not only the network", and
  `FIELDS` left out `absent`, `rates`, `steady` and `notes`. The consequence a reader met: the artifact's
  report stated "78 below the absence threshold" and its page section showed none of them, while the
  command line's message for that condition says "The report lists them". `absent` is a network of its
  own, which is why it was the one lost at the defaults: the other fields pass through as JSON and it
  needs serializing the way `network` does. Measured on a live All derivation round-tripped through the
  format, the page section now matches the live result exactly where it previously vanished, and the
  payload is 0.46 MB. `tests/test_published.py` checks `FIELDS` against what `run_query` actually returns,
  so the next key added cannot disappear in silence, and an artifact written before this still loads.
- **Three `meta` blocks were present and wrong under the integrated form** (#215, and the mechanism of
  #194). Present and wrong is worse than missing, because a reader trusts them.
  - `meta.no_growth` was built from the settings for every derivation, so a form with no such rule
    published `{"applied": true, "obligate": 0, "abolished": 0}`. A reader of the published All artifact
    concluded the rule had run over every study and found **no organism in mGrowthDB that grows only in
    the presence of a partner**. The comparison finds 15 on the same corpus the same day. The block now
    comes from the derivation, as `statistics` and `provisional` already did, and a derivation without
    the rule says so and carries no count, because a 0 there reads as a measurement. It also says where a
    censored arc under that form does come from, since #201 means one can exist.
  - `meta.growth_rates` appeared while `settings.report_rates` was recorded false, and the README stated
    the contract the other way round. Under the integrated form the rates are a product of the same fit
    that gives the arcs rather than a stage to ask for, so the README now says that.
  - settings the derivation does not read were recorded as if they had been used: a reader saw "Include
    drop-out communities: on" where that form derives none, and `--metric auc`, `max` and `growth_rate`
    gave byte-identical networks while the recorded value changed. The derivation names them,
    `meta.settings_not_used` carries them so a reader of the FILE sees them too, and the report and the
    page mark them rather than printing them as used.
- **A total suppression was dropped as "no interaction" instead of being censored** (#201, Karoline's
  decision of 2026-10-11: "I agree on censored"). Under the integrated form an arc's strength is
  `log2(1 + A_ij x_j / r_i)`, which is undefined once the fitted effect reaches -1, so the strongest
  inhibition the form can express has no ratio. That `None` reached `absence`, whose first test on a value
  is `if not mean: return ABSENT`, so the arc was removed from the network, counted under the absence
  threshold, and given a hard `0` in the gLV cell, which a reader takes as no effect rather than as no
  number. The arc up to 99 per cent suppression was published, and strongly; at total suppression it
  vanished. It is censored now: kept, `NA` in the cell, with `bound_rule` saying the statement is the
  fit's and `strength_bound` None, because nothing measured a bound. **No arc on the live corpus reaches
  that boundary today**, so no published network changes; the defect was reachable rather than firing.
  The `outcome` is `abolished`, which already means the target grows only without the source, and
  `bound_rule` is what separates the fit's statement from the no-growth rule's measurement. METHOD_NOTES
  said the integrated form can produce no censored arc and no `NA` cell, which is no longer true, and its
  `derive.py` occurrence count was already one short.
- **A non-finite number in an Advanced settings box produced JSON that R and every strict parser refuse**
  (#195). `float()` accepts `nan`, `inf` and `1e999`, and nothing checked the result was finite, so the
  value was echoed back to the form as the setting in force and copied into `meta.settings`, where
  `json.dumps` writes the bare tokens `NaN` and `Infinity`. RFC 8259 section 6 forbids both, so R refused
  the whole file, `/glv.json` included, which is the URL the help page gives for `grownet_glv(...)`, while
  grownet's own `validate` accepted it, because Python's json module reads the specials by default. Each
  of the five fields now falls back to its default, as any other unreadable value does.
- **A kept response was written through whatever was at its path, and not atomically** (#197). The name is
  sha256 of a public URL, so it is guessable, and `GROWNET_CACHE` is documented as a free-form override
  whose natural value on a shared machine or a CI runner is a path under `/tmp`. A plain `open(path, "w")`
  followed a symlink planted there and overwrote a file outside the cache directory. The write now goes to
  a temporary name beside the target and is renamed onto it, which replaces a link rather than following
  it, and makes the write atomic, so an interrupted run leaves the old entry or the new one and never half
  a JSON document.
- **The remembered address family was never cleared, so a network change cost the full timeout on every
  connection** (#198). `_connect` gives a remembered family the caller's whole timeout, on the reasoning
  that it is the one expected to work, and nothing removed the entry when it stopped working. That is the
  situation the fallback was built for, and in it the memory was worse than none: 30 seconds per
  connection against the 17.5 seconds of operating-system patience #184 measured and removed, and the
  entry survived the failure, so every later connection paid it again. A failing family is now forgotten,
  and the next connection treats both as unproven.
- **The test for that refusal called the function by hand**, so it supplied the `before` argument the
  product has to pass: removing that one wiring line left the test green while the refusal went back to
  blaming the second box. Found by a pass that attacked every new test with the regression it claims to
  catch. It now drives `interactions_from_replicates` with a chemostat study named in the second box
  first, using the helpers this file already has, and keeps the hand call for the two branches a real
  study cannot easily produce. Verified by removing the wiring and watching it go red.
- **A censored arc whose non-growing set has no measurable start published `bound_rule: ""`**, and the
  rule that explains it was computed and thrown away. `no_growth_bound` returns "the no-growth rule left
  no measured start to bound this set by" and `bounded_strength` discarded the string with the value; on
  the live corpus that is the *S. thermophilus* arc, whose STneg monoculture starts at 0 in every
  replicate. `bound_rule` is the only field that can say why a censored arc has no bound, and
  `matrix._reports_an_extreme` tells its five shapes apart by exactly this field, so an empty one made a
  fresh arc indistinguishable from a network saved before the machinery existed. 0 of 15 censored arcs
  carry an empty rule now.
- **`two_replicates` was defined by a spread that nine of the fifteen censored arcs do not have.**
  `README.md` said it marks an edge "whose sd rests on two values" and the legend said "the spread rests
  on two values per side", while those arcs carry `sd`, `se` and `effect_over_sd` all `None`, and on seven
  of them the count on the censored side is the number of replicates that did **not** grow. The caution is
  decided from the counts alone, which is a derivation behavior the collaboration owns, so the three
  places that describe it are corrected rather than the arcs that carry it: it says how few replicates a
  side had, and says that a censored arc has no spread to rest on.
- **A refusal named the second box when the growth measure was the cause** (and printed "study this
  study"). Naming A6 of SMGDB00000005, a chemostat, answered "no experiment of this study matches the
  media, experiments or studies entered", while the same command with `--metric max` derives from it: the
  cultivation-mode filter runs first and empties the list that the selection is then tested against, so
  the refusal a reader acts on sent them to retype the box when the fix is the growth measure or
  `--include-non-batch`. The unfiltered list is now used for the diagnosis only, and the message says the
  experiments were left out before the box was read and points at the reason above it. A selection that
  genuinely matches nothing still says so. `study_ids_of` returned the words "this study" and its one
  caller prefixes the result with "study ", so an emptied list printed "study this study" twice; the
  fallback is the caller's now and it uses the study id it already holds.
- **The format manifest recorded the one id no release carried and omitted the two that releases did**
  (#249). It held `/v2`, which `model.py` says in as many words was never tagged, and not `/v0` or `/v1`,
  which shipped in 0.1.0 and 0.2.0, are still accepted by `PREVIOUS_SCHEMAS` and are in the published
  schema's enum. Its own `_how` says the entries "are the record of what each released format carried",
  so the statement was false in both directions, and a reader using the manifest to learn what a `/v1`
  document declares got nothing. The gate only ever reads the entry for the current `SCHEMA`, which is
  why nothing noticed. Both are reconstructed from the `v0.1.0` and `v0.2.0` trees by reading their
  `model.py` rather than by hand: `/v0` with 29 edge, 7 node and 4 study fields, `/v1` with 31, 7 and 4.
- **Two tests on this branch asserted less than their names claim**, found by a pass that attacked every
  new test with the regression it claims to catch. The download-route test requested five **GET** routes
  and never POST `/glv`, which is the fourth route its own docstring names, so removing that route's
  `_gone` call left it green; and every request used an unknown job id, which always takes the "gone"
  branch, so the **running** case, which is what `_gone`'s docstring is actually about, was never
  exercised. Both are covered now, and reaching the running case needed the fixture to hand over the real
  handler class, because `serve` builds a subclass with its own `state` and planting a job on
  `gui._Handler` never reached the running server. The settings-mark test asserted a phrase that was
  already true, because the test helper forces `include_absent` off its default: it held for a query with
  no keyword at all and said nothing about the threshold. It isolates the threshold and asserts it is
  **named**. Each was verified by applying the regression and watching it go red.
- **Any non-ASCII character in `token=` closed the connection with no response at all** (#246).
  `secrets.compare_digest` raises `TypeError` on a `str` holding non-ASCII, the exception escaped
  `_authorized`, and the browser showed its own "site can't be reached" rather than the token page that
  function exists to show (Karoline, 2026-10-04: "localhost:8791 shows an error"). `secrets.token_urlsafe`
  emits `-` and `_`, so any tool that autocorrects a double hyphen to an en dash on the way to a reader
  produces exactly this, and it failed worse than the case the code was written for. The comparison is on
  bytes now, and a mangled token answers 403 with the token page like any other wrong one.
- **Four download routes told a reader to tick a box they had already ticked** (#246). `/rates.csv`,
  `/glv.zip`, `/glv.json` and the gLV form went straight from "no rates" to "tick Report growth rates and
  run the search again" for a search that was pruned **or still running**, with rates on. `_gone`'s
  docstring states the rule they broke: a running search "must not be told to run again: it is running,
  and saying so sends a reader to repeat work that is already under way". `/download` and `/report.txt`
  already called it. These are the slow routes, and a gLV run with rates is the search a reader least
  wants to start twice.
- **The gLV example button inherited whatever Advanced settings were left in the form** (#246). The
  Example button beside it was changed on 2026-10-09 for exactly this, and its comment says why: "It used
  to keep them... Either gave an empty network with nothing on the page to say why" (Karoline). Pressing
  gLV example with an absence threshold of 9 still in the form filled the boxes, ran, and produced no
  network and no package, against a caption promising a package that simulates. It starts from the
  defaults now, as Example does.
- **A setting changed and forgotten left no mark on a result that still had arcs** (#250). Advanced
  settings was always collapsed, and the result section named a changed setting only when the network came
  out empty, because that notice runs from the empty-network reason alone: so the one case where numbers
  leave the page under a changed threshold was the case the page did not mark. The block opens with a
  count when anything is off its default, and every result names them in one line.
- **The Cytoscape table dropped `taxonomy` and `model_ref`**, which the neutral file and GraphML both
  carry, against the claim in the same file that this payload names every field and against
  `network_json`'s own docstring ("every node and edge attribute becomes a column"). grownet populates
  neither today, so nothing is lost on a live run, but a network given a lineage or a metabolic-model link
  by hand lost both on the way to Cytoscape, and `model_ref` is named for the downstream consumer the
  neutral format exists to serve. Found by comparing the two emitters rather than by reading either, which
  is how the same asymmetry was found for the three error components. `tests/test_export.py` now asserts
  set equality between the payload's columns and the `Node` and `Edge` records, so the next field cannot
  stop at the table.
- **The gLV payload published the fitted row count under the field named `replicates`** (#259), where
  `growth_rates.csv`, the other emitter of the same numbers, published the monoculture replicate count.
  `replicates` has meant monoculture replicates since 0.2.0, which is the rule stated over `rates_csv`,
  and a derivation that merges fitted rows keeps the row count in `n` with `n_label` precisely so the two
  are not confused. On a live `--all --glv-mode` run the payload said 1 and 2 where the zip said 3, and
  the R package reads the field straight through, against a docstring promising "the same numbers as the
  zip" and a README allowing a difference in the fifth significant digit. It bit the integrated form only,
  which is the one gLV mode selects: under the default derivation there is no `replicates` key and both
  routes fall back to `n`, which is why nothing noticed. The row count is deliberately not added beside
  it, because a new field would move `grownet.glv/v1`; it is in `meta.growth_rates` for anyone who wants
  it.
- **The GraphML, the Cytoscape payload and the viewer joined `community` with a space, and 115 of 145
  arcs of the default corpus could not be split back** (#245). `community` holds node ids, and a node id
  under identity `name` is a lowercase species name, so a 14-member community read as a 16-member one
  whose two extra members were word fragments (`lachnoclostridium`, `symbiosum`). It is the field a reader
  needs for exactly the arcs that depend on it: a drop-out arc's own text says the effect may run
  "directly or through the others", and the others are this list. Joined with `"; "` now, in all three
  routes, as `notes` and `merged_pairs` in the same emitters already were; 0 of 145 fail to split.
  The rule for any future list whose members can contain a space is written where the "space-joined
  community" claim used to be, and the four still joined with a space carry no such value today, which was
  measured.
- **Every censored arc's `bound_rule` printed a start abundance and a window with no unit** (#248), and
  one field carried 105.8 Cells/mL on one study and 1.44e+07 CFUs/mL on another while naming neither.
  `GrowthCurve` refuses to exist without both units, so they were in hand at that point, and the report's
  next clause on the same arc already prints the partner's abundance with its unit. `strength_bound` is
  the only number a reader has for a censored pair and this rule is the only thing that says what it came
  from. All three metric branches now carry them, including the rate bound, which printed `0.001408` with
  no `1/h`.
- **The page promised a matrix cell the CSV did not hold** (#248). `matrix.counts` counted self pairs and
  `rows` writes the diagonal there, so with `--merge-genera`, which produces within-genus arcs by
  Karoline's own choice, the page said 45 cells over 17 organisms and the file held 44: the lost cell was
  written as `0`, the same token as the 245 pairs where no comparison was attempted. `counts` reports them
  apart now and the page says how many arcs have no cell and why. Verified on the live corpus: 44 against
  44.
- **The `grownet_glv()` address in the R package's own documentation omitted `job=`** (#251), so following
  it served whichever search the browser last looked at: two tabs, two searches, and the job-less address
  returned a different system's parameters each time with HTTP 200 and the right format. The page prints
  the address with its job, and the three documented examples now say so and say why to copy it rather
  than type it.
- **The R package's `glv_write` wrote three of the download's sixteen rate columns**, under a doc
  promising "the same three files grownet's download holds". A reader who kept its output beside their
  analysis, which is what the documentation says it is for, silently dropped the estimator, the lag, the
  carrying capacity and its provenance: the columns the `README.txt` written next to it tells them to
  read. Every value was already in the payload's `growth_rate_detail`, so it now writes them, with the
  doubling time derived as the download's last column is. The documentation also said "three files" where
  the download holds one matrix per abundance unit, and says so now.
- **Two published statements about `sd` and `se` said what the code's own comment says is false** (#260).
  `help.py`'s meaning for `se_replicates` and METHOD_NOTES both asserted that "the tool's own relation
  se = sd / sqrt(n) holds", and METHOD_NOTES added "`sd` is `se * sqrt(n)`", which is the formula
  `integrated.py` abandoned on 2026-10-07 and records in a comment as one that "never held for two
  variance components": the monoculture stage's error is shared by every replicate of a row, so its
  variance is never divided by n. Measured on all twelve arcs of a live `--glv-mode` run, `sd / sqrt(n)`
  is out by up to a factor of 2.06, while `se` reproduces exactly as the square root of the component
  variances added. Both now say that. METHOD_NOTES also said "both halves are published", naming two of
  the three components: `se_rate_selection` is published too.
- **The caveat naming which direction the gLV diagonal runs had no test that could see it** (#260). The
  assertion read `== "fitted: -r_i / K_i" or "fitted" in caveats["diagonal"]`, and the second half passes
  for any string containing "fitted", so inverting the integrated entry back to the comparison's
  direction, the correction #231 exists for, left the suite green. It now asserts the exact string for
  the derivation in hand, and that the two derivations differ.
- **The help-command guard applied one of the three pre-flight checks a run applies**, found by a pass
  that attacked every new test with the regression it claims to catch. `_derive` consults the rate flags,
  the settings bounds and, on the search path, three further guards; the test called the rate flags
  alone, so adding `--species` to the printed `--all` line, the most ordinary editorial slip for it,
  exited 2 with the whole suite green. The search path's three guards are pulled out of `_derive_species`
  as `_species_flags`, so one function holds them and the test reaches all of them; a guard added there
  in future is consulted by the test without anyone remembering to add it. Verified by making that slip
  and watching the test go red.
- **Gate check 6 said emitted networks validate against the shipped JSON Schema, and it runs the
  dependency-free validator** (#249), which this release documents as a subset of that schema: a
  hand-written network passes `grownet validate` and fails the schema nine ways. The claim stood in the
  gate's own summary of its checks, in the function's docstring and in the message it would print. All
  three say which validator runs now. No emitted network violates the schema today, which was measured,
  so this was a false claim about a guard rather than a wrong output, and the version that would make the
  original claim true (walking the schema's own keywords over the document, both of which are in hand
  there) is named in the docstring for whoever wants it.
- **The help page's own guard read `<pre>` blocks only** (#249), and the page prints four more commands
  in inline `<code>`, among them the gLV walkthrough, which is one of the three places #234 says this bug
  was already fixed once. Removing `--live` from that inline command left the whole suite green while the
  printed command exited 2. Both elements are read now, 13 commands against 9, the floor is the real
  count so losing a block fails rather than quietly checking less, and the inline case was verified by
  breaking it and watching the test go red.
- **The help page told every reader that All spares "about 1,300 requests"** (#249). This release
  re-measured that quantity for `docs/METHOD_NOTES.md` and corrected it there, and walked past the page a
  non-developer reads: it is 1,926 cold and 54 warm, counted at the client's own send. Both figures with
  a pointer to the command now.
- **Five statements promised the residual of every fit, including every gLV package README, and no output
  carries it** (#230). `_least_squares` computes it and `fit_row` and `two_stage` drop it; there is no
  residual field on an edge, in the schema, in GraphML, in Cytoscape or in `r/`. The gLV package was the
  sharpest: its own README said each cell can be traced to its fit by the condition number and the
  residual, and the condition number is on the network edge rather than in the zip, so the zip could not
  be traced to its fit at all. The promises now name what exists, `fit_condition`, `fit_r2` and
  `fit_null_r2`, and the package README says a cell is traced through the network it was built from.
  Emitting the residual would add a field and move the format id, so that is not done here.
- **`caveats.diagonal` stated the retired direction, and the R package repeated it in four places**
  (#231). It was one unbranched string, "fitted: -r_i / K_i, with K_i the organism's own plateau", which
  is the comparison's direction; under the integrated form `A[i][i]` is the fitted parameter and
  `K_i = -r_i / A[i][i]` is derived from it, which `matrix.py` itself calls "the opposite direction"
  twelve lines from where both were written. So a gLV package built by the integrated form carried the
  retired statement in its `caveats` while its own README carried the correct one. `DIAGONAL_CAVEAT` now
  holds both and is selected by the derivation, verified on live payloads of each; `r/R/use.R`,
  `r/man/glv_matrix.Rd`, `r/README.md` and `r/R/payload.R`'s fallback say that it depends on the
  derivation, and the R fixture that pinned the retired text is labeled with which arm it is.
  Same shape as #211 item 1, in the places #211 did not reach.
- **Four statements about the project's own guards were stronger than the guards** (#235).
  `schema.py`'s module docstring said the dependency-free validator "enforces the same constraints" as
  the shipped JSON Schema: a hand-written network passes `grownet validate` and fails that schema nine
  ways, because `validate_document` checks no numeric type, no `minimum`, no `maximum` and no string
  type. The viewer-vocabulary guard covered 4 of the 7 vocabularies and `STATUSES` was not among them,
  although its own docstring cites a `status` value arriving as a reason it exists; it covers seven now,
  and the three left out say why. `ASSERTS_DEFAULT` caught 1 of 8 natural ways to call a deriver the
  default, including "By default, X derives every network" although `runs by default` was in the pattern,
  because it is word-order sensitive; all eight are caught and the sentence naming both forms still
  passes. And `published.fresh`'s `settings` argument defaults to `None`, which skips the derivation
  check that the docstring makes the point of the function: `fresh(p, now)` was True on the artifact that
  `fresh(p, now, DEFAULTS)` refused. No shipped path does that, and it is written down rather than left
  to be found again.
- **Four reader-facing texts stated the published artifact's condition as age only** (#235), after #199
  added the derivation condition: `README.md`, the help page, `run_query`'s docstring and
  `--no-published`'s help. A reader at the defaults could be refused the artifact on a condition no
  document stated.
- **The documentation was run literally and three things in it did not work** (#234). `CONTRIBUTING.md`'s
  development setup said `cd grownet` where the clone makes `crossfeed`, and did not say which Python, so
  it failed at its second line for every developer the README sends there. A help-page example exited 2,
  which was **the fourth copy of that bug** after the CLI epilog, the README and the gLV walkthrough; no
  test ran what the help page prints, so a test now parses every command on it through the real parser
  and the run's own argument resolver, which is what the previous three fixes lacked. And `README.md`
  named `grownet-<version>-windows.zip` where every release carries `grownet-v<version>-windows.zip`,
  which `RELEASING.md` and the release check both had right.
- **A control that can empty the network was listed in the guard and could never fire**, and the two
  tests of these guards asserted a subset of what they claimed. `_EMPTYING` held seven entries and the
  seventh, `min_replicates`, is not a page setting, so the loop skipped it on every call: dead code no
  test could see, because the test asserted three of the seven by hand. Deleting the other four left it
  green and #220 returned for four real controls. The entry is gone, the test loops over `_EMPTYING` for
  the behavior **and** asserts its membership explicitly, because looping over a constant cannot notice
  the constant shrinking, which the first attempt at this fix got wrong. The sibling test asserted three
  of the five flags in the negative-value guard and never asserted the `--no-growth-alpha` bound at all;
  it names the flags from the guard's own list now. Both were verified by applying the deletion and
  watching them go red.
- **An incomplete run exited 0 on the species and All paths** (#247), while `derive <a bad id> --live`
  exited 1 for the identical failure: the species path collected the 404 into `errors`, printed it, and
  returned 0, so a script could not tell a complete run from an incomplete one. It says the run is
  incomplete and returns 1 now, and says what the network does hold. This is safe to key on `errors`
  only because that list is fetch failures and nothing else: the advisory messages travel in `notes`,
  which is the split this release makes, and the test asserts both halves, because keying on a list
  holding both would fail a **complete** run. The first version of that test recomputed the condition in
  a loop and would have passed against any implementation; it drives `_derive_species` with a stubbed
  `run_query` instead, and fails when the rule is changed to read `notes` as well.

  Not fixed here, and filed: what the FILE says about its own completeness. `meta` carries no record that
  a study could not be read, and `meta.studies` lists the unreadable study as a source, so the artifact
  asserts provenance it does not have and `validate` passes. Recording it adds fields, which moves the
  format id, so it is Karoline's and Craig's call (#247).
- **`--no-growth-alpha` took any non-negative number, and 5 was published as the level the test ran at**
  (#250). The sibling `--max-adjusted-p` refuses 5 with a message. An alpha of 5 makes every replicate
  set count as grown, so the no-growth rule, the only source of the censored and obligate arcs, is
  switched off while `meta.no_growth` records `"alpha": 5.0`. The help documents exactly one way to switch
  it off, which is 0. It is bounded at 1 now, with 0 still the documented off switch.
- **The command line still did not name the setting that emptied the network** (#250, the command-line
  half of #220). `--spike-factor 1` is a legal value, so no refusal applies, and the "most common reason"
  the message printed is a line that is also present at the defaults, where the same study yields an arc:
  so the setting that did it was the one thing the message did not mention. The page's own
  `_settings_to_try` is a pure function over a settings dict and `_settings_of` already builds that dict
  for every command-line path, so the empty-network message names them too, and says nothing at the
  defaults.
- **An unused id in Exclude these studies went into `errors`**, which the empty-network reason reads as
  "mGrowthDB could not be read", so the advisory message added here would have blamed the database for a
  reader's own setting. It travels in `notes` beside the steady-state messages instead, which is the list
  `_empty_reason_core` does not consult.
- **A setting could empty the network while the tool blamed mGrowthDB** (#220). `--min-studies 2` counts
  the studies behind a merged arc, so with nothing merged every arc counted as 1 and all of them were
  removed; the page then blamed the species filter, said "the species do not affect each other by that
  rule" while measured arcs were being discarded by a different control, and finally blamed mGrowthDB's
  replicate structure. The setting was named in exactly one place, the report's `5 arc(s) below 2
  studies`, and only with `--report`. The command line now refuses that combination and says to add
  `--merge-arcs`, and any empty search on the page names every setting the reader changed that can empty
  a network on its own, with what to try. `--spike-factor 1` and `--rate-window 1` are the same shape and
  are covered by the same two changes.
- **The command line accepted numbers the page clamps** (#221). `--rate-window -3`, `--absence-threshold
  -1`, `--no-growth-factor -2` and `--spike-factor -1` each ran and exited 0, and the negative value
  traveled into `meta.settings` as the provenance of the run: one run reported its own threshold as
  "|log2 mean| < -1 * sd". They are refused with the bound now, which is the half of "refuse or announce"
  a command can do and a form cannot.
  **A non-finite one is refused with them** (#258): `nan` and `inf` are numbers to `float()` and pass a
  `value < 0` bound, because both comparisons are False, and `json.dumps` then writes the bare `NaN` and
  `Infinity` into `meta.settings`. RFC 8259 section 6 forbids both, so R refuses the whole network while
  grownet's own `validate` accepts it, Python's json module reading the specials by default.
  `--max-adjusted-p` already refused them through its own type, which admits only `0 < value <= 1`.
- **A mistyped `--exclude-studies` id was dropped in silence and recorded as applied** (#221).
  `SMGDB0000002`, one digit short, left the study in the search while the report filed with a paper said
  it was excluded. An id that matches no study searched is now reported, like an unusable entry in the
  species box, and the ids that did apply are still applied.
- **The wrong port was reported as out-of-date software** (#221). Pointing `--cytoscape-port` or
  `--r-port` at any server answering an error status was reported as that program refusing the data, with
  an instruction to upgrade it: grownet's own page, which answers 403 without a token, produced "Update
  Cytoscape to 3.8 or later". Both now ask who answered first, CyREST at `/v1/version` and the R listener
  by its own plain-text reply, and say "something on port N answered 403 Forbidden, and it is not
  Cytoscape" when it is not.
- **`--rates` or `--glv` with no computable rate threw away every diagnostic** (#221) and pointed at a
  report that was only written with `--report`. It returned before the skipped-pair list, the
  absence-threshold note, the low-quality note, the sources block and the "NO interactions were derived"
  explanation, so asking for more output gave 7 lines of stderr where asking for less gave 74, including
  35 copies of the exact cause. The diagnosis is printed and the exit code is carried to the end of the
  run, and the message names the flags that wrote nothing and says where the reasons are.
- **All said it ignored the boxes, and it reads the second one** (#193). Narrowing All by a study or
  medium in the second box is deliberate and documented (`run_query`, Karoline 2026-09-28); the caption
  claiming otherwise and the heading "All of mGrowthDB" were the false half. The gLV example button fills
  that box and leaves it filled, so pressing gLV example and then All reported a two-arc network of one
  study as the whole database. The heading now says "All, narrowed by the second box" and names what it
  matched, the caption says it ignores the species box, and the box's own hint says All reads it and to
  clear it for the whole corpus. The bar's text has a length Karoline set and a test pins it, so the
  detail is in the hint rather than the bar.

  **And the report embedded in that page still claimed the whole database**, found reviewing this branch.
  `report.py` wrote "query: all of mGrowthDB (every study, with every partner)" unconditionally, three
  lines above its own "Media, experiments or studies" line, so one file contradicted itself and
  `/report.txt` and the download said it too. **The test written for exactly this missed it on letter
  case**: it asserted `"All of mGrowthDB" not in page` and the report writes lower case. The report takes
  the same two controls now, the command line's own run label does too, and the test reads the page
  case-insensitively and asserts the containing phrase rather than a bare study id, which reached that
  page from five other places.
- **Three tests on this branch could not fail, and were rewritten so that they can.** A review pass
  attacked every test added in the last two days by constructing the regression each claims to catch.
  The settings test rested on two assertions that are true of their own construction, because
  `_settings_of` returns `{**DEFAULTS, ...}`: dropping three keys so they fell through to the defaults,
  which is verbatim the defect its docstring describes, left it green. It asserts every one of the 23
  page settings is moved by its own flag now, and counts them, so a new setting without a case fails.
  `about_a_pair`'s only negative case had a reason that does not contain `AVERAGE`, so that half of the
  predicate was untested; both label shapes are asserted against it now. Each was verified by applying
  the regression and watching the test go red.
- **"pairs the data did not support (186)" counted 97 notes about the data and 31 conditions that did
  produce arcs** (#232), and the first version of this fix made it worse before it made it better:
  `about_a_pair` told the two kinds apart by the label's punctuation and knew only one of the two shapes
  the code writes, so on SMGDB00000013 the report read "pairs the data did not support: none" while
  listing seven of them under a heading saying they are not pairs. `derive.py` writes
  `{a} with {b} [{cond}]` for a pair whose sets could not be compared and `{source} -> {target} [{cond}]`
  for the no-growth and unusable outcomes; both are declared as `adapter.PAIR_SEPARATORS` now, and a
  third separator added somewhere is recorded there as a known gap rather than left to be discovered. `adapter.condensed` folds the average-replicate notes to one line per
  experiment, keyed by the experiment, and they were counted under a heading about pairs: the report
  called a condition a pair that gave no edge 254 lines after reporting an interaction derived from it.
  The report, the page and the command line now separate pairs from notes on the data read, and the
  "skipped N pair(s)" message counts the pairs. The page also said 186 and showed 50 with no marker; it
  says "showing 50 of N" and points at the report.
- **An empty network caused by the reader's own setting was reported as "mGrowthDB could not be read"**,
  in a run where mGrowthDB answered every request. `_empty_reason_core` reads `errors` as a fetch
  failure, which it used to be and only be; the messages added here and in #243 for a check that could
  not run and an id that matched nothing went into the same list, so the lead sentence did the exact
  thing #220 and #243 exist to stop. Advisory messages travel in `notes` now, which the page shows beside
  the errors and `_empty_reason_core` does not consult.
- **The page accepted the steady-state check without growth rates, ran nothing, and said it was on**
  (#233). The command line refuses that combination and names the remedy; the page ticked the box, scored
  nothing, printed "Check against chemostat steady states: on" and wrote `steady_check: true` into the
  downloaded network. It now says what the command line says, and a run that asked for the check with
  rates on but no computable rate says that instead of leaving "on" as the only trace.
- **Two derive paths recorded different settings, and both recorded `steady_check` wrongly** (#233),
  and the first version of the single builder left `exclude_studies` and `only_entered` to come from the
  page defaults, which turned a setting the report did not mention into one it stated the **opposite**
  of: `derive <STUDY> --exclude-studies <that study> --all-partners` recorded "Exclude these studies:
  none" and "Only interactions between the species entered: on", having searched the study and kept every
  partner. Both are in the builder now. Recording them is not enough on its own, because the report
  would then say a study was excluded while the arcs come from it, so a bare study argument with
  `--exclude-studies` or `--all-partners` is refused: those flags narrow a search over several studies
  and the help already said they apply with `--species` or `--all`. `conditions` was the other key left
  out of that builder, and the one whose two paths disagreed in VALUE: the single-study path joined
  `--conditions "WC" "mucin"` with a space, and space is the one separator `selection.parse` does not
  split on, so the record read back as one medium named "WC mucin" that matches nothing while the run used
  the two. It is in the builder with the page's own one-per-line encoding.
  `derive <STUDY> --live` wrote 20 keys and the species path 23, the difference including
  `include_absent` and `steady_check`, which are n/a on neither; and the species path took `steady_check`
  from the page defaults rather than from the flag, so a run that scored a chemostat recorded that it had
  not. One builder for every path now, 24 keys on both, verified on live runs of the same study, and a
  test reads it through the real parser rather than a copy of the key list.
- **Nine measured claims that no longer reproduced are corrected, and each now carries the command that
  produced it** (#223, #219). None is a change to the code: every one was a sentence that had stopped
  matching what the tool does, which is the one thing internal correctness does not tolerate. Re-measured
  live on 2026-10-11, and the split #223 found holds: the claims a command prints about itself were fine,
  and these are the hand-assembled ones.

  | where | said | gives now |
  | --- | --- | --- |
  | `rates.py` | easylinear matched mGrowthDB on "43 of 46 within 10%" | **119 of 119** on SMGDB00000004, median ratio 1.0001, and **2132 of 2161** corpus-wide |
  | `help.py` | "190 of 192 curves" | **2132 of 2161**: the proportion held, the denominator was an order of magnitude off |
  | `METHOD_NOTES` caching | a run sends 3738, "an unchanged corpus costs the 54 study records and nothing else" | cold **1926**, warm **54**, which is 25 study records plus **29 id-crawl probes that answer 404 and are never cached**, with 1872 reused |
  | `METHOD_NOTES` rate mismatch | two *L. delbrueckii* arcs imply **-83.5 and +129.8** per cent | **-21.56 and -21.74**: same sign, 0.2 points apart |
  | `METHOD_NOTES` coverage table | comparison 30 arcs / 8 rows / 10 cells, integrated 23 / 6 / 9 | comparison **24 / 8 / 8**, integrated **12 / 7 / 7** |
  | the same table's recorded command | `derive SMGDB00000007 ... --steady-check`, "that study alone" | gives **5 arcs over 3 rows** and **4 over 3**: that study holds three organisms, so it cannot produce 8 rows, and the figures were corpus-wide |
  | `METHOD_NOTES` starting densities | "up to 7.43 (SMGDB00000014's *A. tumefaciens*, 1.5e5 against 6.6e5)" | 6.6e5 / 1.5e5 = **4.4**; the 7.43 belongs to the *S. thermophilus* pair named six lines later |
  | `METHOD_NOTES` and `test_measured_bound.py` | "11 of 12 inside the quantified range" | **12 of 12** |
  | `LIMITATIONS` entry 2 | "of 123 monoculture fits ... three imply a doubling slower than 24 hours" | **8 published rate rows, none** slower than 24 hours; the study those three came from now yields no network and no rate at all |

  **Three further claims in the same bullet were re-measured after this branch was first pushed**, found
  reviewing it: the median implied mismatch is **27.05 per cent**, not 19.2, which widens the gap against
  the 8-to-16 noise floor the paragraph compares it with by 69 per cent; the two *L. delbrueckii* arcs
  carry `se_rate_selection: None` and the `rate_unchecked` caution, so they take **one** stage-1 rate and
  the premise of the grouping argument cannot be read off them at all; and the starting-density census was
  wrong in four figures at once, **16** comparisons with a median of **2.14** and **4** above 3, against a
  stated 39, 1.17 and 6, while the same bullet ten lines below had 2.16 and 4 of 12 right all along. That
  census is also in `integrated.starting_densities`'s docstring and is corrected there.

  **And two commands in this branch could not print what they were attached to.** The LIMITATIONS one
  needed `--rates`, because the message it quotes is what refusing to write that file says; without it the
  run exits 0 with an empty network. The steady-state one needed `--report`, because the figures are in
  the report and the recorded command asked for neither it nor the zip. Both are the class this branch
  exists to correct, caught inside it.

  **Two are worth more than a corrected number.** The coverage table's own note says a missing command
  made two readers take it for a fabrication, and the command added to fix that was the wrong one, which
  is how a record decays twice in the same place. And the rate-mismatch paragraph drew a method argument
  from the two figures that have changed: two arcs moving the same way by nearly the same amount is what a
  shared rate error would produce, which is the opposite of what the paragraph concludes. That is recorded
  and not rewritten, because the conclusion is a method judgement and the decision on #155 item 1 was
  Karoline's.
- **The 0.3.0 notes state a steady-state measurement that does not reproduce** (#219), and a tagged entry
  is never rewritten, so the correction is here. They say the integrated fit "lands all three organisms at
  0.41, 0.73 and 2.69 times the observed abundance". Re-measured live on 2026-10-11 with that entry's own
  command, `derive SMGDB00000007 --live --glv-mode --derivation integrated --steady-check --report <file>`, against
  SMGDB00000005's control: *B. thetaiotaomicron* **washes out** while the chemostat holds it at 5.285e+08,
  *B. hydrogenotrophica* lands at **299.8x** observed and *R. intestinalis* at **119.6x**, and the fitted
  interactions are **worse than no interactions at all** on both (34.8x and 2.878x with every interaction
  set to zero). The other half of the same sentence does reproduce: the comparison gives 1.592x, washes
  *B. hydrogenotrophica* out, and 3.194x, against the published 1.60 and 3.26.

  **A held-out prediction that misses by two orders of magnitude is not a defect in this tool**, which is
  Karoline's standard of 2026-10-10: showing how hard interaction inference is from observational growth
  data is what it is for, and reporting the miss is the tool working. What was wrong is that
  `CHANGELOG.md` and `docs/METHOD_NOTES.md` stated different numbers for the same measurement inside one
  tag. The gLV statistics themselves are unchanged and are not being re-argued.
- **The source distribution now carries the two registers the test suite reads**, `docs/METHOD_NOTES.md`
  and `docs/LIMITATIONS.md`, and a test keeps `MANIFEST.in` honest about that. A test that reads a shipped
  document makes it a dependency of the suite, and the sdist job is the only one that notices when it is
  not carried, because it unpacks the archive where the repository layout is not there to fall back on:
  the surface guard added for #202 went red there while `make check` was green. The named include is
  deliberate rather than forgetful. Measured first: `recursive-include docs *.md` also ships
  `docs/agents/NOTES.md`, 95,162 bytes of agent working notes, and `docs/DATA_GOVERNANCE.md`, so it is not
  a tighter version of the named line but a decision to publish two more files; `graft docs` adds those
  plus both SVGs; and a recursive rule with `prune docs/agents` works only when the prune comes after it.
  The new test reads the paths out of the suite rather than listing them, so the next surface test is
  covered the moment it is written, and it records that `README.md` ships because setuptools carries the
  declared readme, which is a default rather than a promise.
  Corrected from reviewing that change: the extraction matched only a whole relative path inside one
  literal, and the suite's dominant idiom is a **component join**, so three files it already reads were
  invisible, among them `schema/format_fields.json`, which `MANIFEST.in`'s own comment names as the
  2026-10-08 instance of this exact failure. Both shapes are matched now, 7 paths against 3. The test
  also had no positive control, which is why a promise it did not keep read as kept; it has one, written
  to a temp file. That control is built from variables with one literal per line, because this file is
  one of the files the extraction scans and a tuple of string literals reads as a path join: it caught
  its own control twice while being written, which is the guard working.

  And a third correction, from a pass that attacked every new test with the regression it claims to
  catch: both shapes needed the directory name as a literal **next to** the filename, and the suite also
  writes `DOCS = Path(...) / "docs"` at module level and then `DOCS / "X.md"` inside a test. A surface
  test written that way, which is the most ordinary Python idiom and which `tests/test_legend.py` already
  half-uses, passed unnoticed while reading a doc the manifest does not carry. Module-level directory
  constants are resolved through the AST now, verified by writing exactly that test and watching the
  guard fail on it. The docstring also names the shapes it still cannot see, rather than promising every
  surface test is covered.
- **Three of the gate's checks read nine file extensions, so the viewer and the whole R package were
  never scanned** (#227, measured by Craig's agent on #239). Of 138 tracked files the list matched 108:
  the 30 it skipped were 9 `.Rd`, 8 `.R`, the extensionless `LICENSE`, `NOTICE`, `Makefile`,
  `r/NAMESPACE` and `r/DESCRIPTION`, both `.svg`, and one each of `.gitignore`, `.cff`, `.in`, `.html`,
  `.Rbuildignore` and `.DS_Store`, the largest being `gui/index.html` at 52,570 bytes, which is the whole
  viewer. The list's failure mode is the one nobody can enumerate, the next extension no one thought of,
  and it had cost two misses in four days. What to scan is now decided by content, with a NUL byte as the
  binary test rather than UTF-8 decodability, so a latin-1 file is still scanned and a binary with no
  early NUL yields a false positive rather than a silent miss. 137 of 138 files are scanned now, and the
  one skipped is `.DS_Store`.
- **The gate overstated its own reach in the line a reader takes away from it**: "138 tracked files clean
  across 9 checks" while the content checks read 108 and the merge-marker one 113. It now reports what was
  scanned against what is tracked, and names what it skipped.
- **The gate's `secrets` check required the value to be quoted**, so an unquoted one passed all nine
  checks: a workflow `env:` block is unquoted YAML, and so is `TOKEN=...` in any scanned file, which is
  how a secret is most likely to be written here. The quotes are optional now, and `bearer` may be
  followed by whitespace rather than a separator, which is how an Authorization header is written. A value
  must still be 16 or more characters from the class, so `${{ secrets.X }}`, `$VAR`, `<your-token>` and
  `""` still do not match, and the gate is clean on all 138 tracked files. The check had no test of any
  kind; it has one now, asserting both what must be caught and what must not, with every example
  assembled at run time so that a test of the guard does not trip the guard. **No secret was ever in the
  repository**: this closed a hole in a check, not an exposure.

  Two corrections from reviewing that change. The whitespace-only separator is for `authorization` and
  `bearer` alone, which is how an Authorization header is written: applied to all seven keywords it
  flagged ordinary prose, because one hyphenated word after "secret" or "token" is sixteen characters of
  the class, and this project's house style is long prose Markdown with inline file paths. And the key
  header is `-----BEGIN [A-Z0-9 ]{0,20}PRIVATE KEY` now: DSA, ENCRYPTED and PGP PRIVATE KEY BLOCK were
  missed while the check's own description says it covers private keys, and the first version of the test
  probed one header out of seven. Both directions are measured: 13 of 13 caught, 11 of 11 left alone.

  A third correction, from a pass that attacked every new test with the regression it claims to catch:
  this check's **only** test probed the keywords `token`, `api_key` and `authorization`, so `secret` and
  `password`, half the key/value group, were untested, and narrowing the pattern to
  `(?:api[_-]?key|token)` let an unquoted `password=` line through with the test green. There is a case
  per keyword now, and an assertion that every keyword the pattern names has one, so adding a keyword
  without a case fails.
- **The sentinel's remedy was stated without its exception** (Craig's agent, reviewing #226). The new
  `metric_without` description told a reader that how far from 0 the set was "is on the same arc, as
  strength_bound with the rule that gave it". `derive.bounded_strength` has two paths that return no
  bound, and on the corpus **3 of the 15 censored arcs take one of them**: measured live, two whose rule
  bounds nothing away from zero and one that is zero from its first point. A reader followed the sentence
  and found an empty field with nothing having warned them, which is the same defect class the entry
  above fixes. The description now names the exception and points at `bound_rule`, which says which path
  it was; the matrix already left those three cells `NA` rather than 0.
- **The test for the fitted report line modelled the wrong field**, found by a pass that attacked every
  new test with the regression it claims to catch. It built its edges with `method="integrated:two_stage"`,
  which is `integrated.METRIC`; the `method` field carries `integrated.METHOD`, which begins "integrated
  v1: ln(x_i(T) / x_i(0)) = ...". The test passed only because that string happens to contain the word
  the detection looks for, so rewriting the detection as an equality against the invented string left the
  test green while **every real integrated arc fell back to the unlabeled line a reader divided and
  found wrong**. It uses the real constants now, plus a merged arc, whose method carries "; merged: ..."
  appended afterwards and which the invented-string version would not have labeled either.
- **Three words the tool used about itself claimed more than it computes** (#224, #225, #226), found in a
  review of 0.3.0. No statistic, rule, threshold or published number changes; what changes is that the
  sentences describing them are now true, and three tests hold them there.
- **`strength` and the `metric_with`/`metric_without` pair were documented as one quantity, and under the
  integrated form they are two** (#224). Under the specified comparison `strength` **is** exactly
  `log2(metric_with / metric_without)`, and 0 of 208 corpus arcs depart from it beyond rounding. Under the
  integrated form the pair is the fitted row evaluated with and without the partner's term, from the
  median coefficient, while `strength` is the mean of the per-replicate log2 effects at each replicate's
  own partner level: **16 of 16 corpus arcs differ, by up to 0.42 in log2**, and on 2 the absence
  threshold, which acts on `strength`, lands the other way from the pair. The report printed
  `log2 mean -0.54` and `0.2701 with / 0.4926 without` on one line, so a reader who divided them got
  -0.8669 and found the line wrong. `model.py`, the `strength` and `metric_with` field descriptions and
  the report now name the relation per derivation, and the report gives the fitted pair's own log2 ratio
  beside it rather than leaving it to be computed and doubted. What is exact under **both** is Karoline's
  formula of #123, `(with - without) / partner_abundance`, which is what a gLV cell is built from, and
  that is what the new test pins.
- **`outcome: obligate` was defined in eight places as "the target grows only with the source"**, which
  reads as a claim about the organism (#225). The rule is evaluated per comparison: it says the
  without-set of **that** comparison failed the no-growth rule, and no stage asks whether the target grows
  without the source anywhere else. In the corpus one pair is obligate in two conditions of a study and
  quantified in six others of the same study, **once with the target reaching 1.16e+11 without the source
  against 3.31e+10 with it**, so the artifact carried its own counterexample. The field table, the legend,
  the help page's principle, `derive.py`, `interaction.py`, `matrix.py` and the README now state the
  scope, and a dated note records it under Karoline's decision on #16 without altering her words. A pair
  measured as obligate in one condition and quantified in another is a condition-dependent effect, not a
  contradiction (Karoline, 2026-10-10, on the related sign conflict: "it's of interest and just shows that
  higher order interactions matter").
- **`metric_without` is 0 on every censored arc whatever the metric, and the help page said the 0 was a
  measurement** (#226): "0 means the target did not grow at all there". Under a growth rate the 0 is
  measured, which is what #123 settled. Under `auc` or `max`, and `auc` is the default, the set **did**
  grow and failed a rule about how much, so its value is not 0, and the same arc's `strength_bound` says
  how far: on the corpus all 15 censored arcs are `auc`, all carry 0, and their own bounds put the
  without-side at **up to 65 per cent of the with-side**. The field description and
  `derive.absolute_values` now call the 0 a sentinel for the set the no-growth rule rejected, and point at
  the bound for how far from zero it was. The value is unchanged, since changing what the field means
  would move the format id.
- **Every relative link in the README was dead on PyPI, and the legend image was broken there** (#192).
  The README is the long description on <https://pypi.org/project/grownet/>, and PyPI does not rewrite
  relative URLs the way GitHub does, so all fifteen resolved against the project page: the limitations
  statement, the method notes, the data-governance statement, `SECURITY.md` and its private route for
  reporting a vulnerability, the contributing guide, the JSON Schema, the R package's README, and the one
  picture of the visual vocabulary, which rendered as a broken image. They are absolute now, and the image
  comes from `raw.githubusercontent.com`. It had shipped this way in 0.1.0, 0.2.0 and 0.3.0.
- **The published error model said the standard error has two components; it has three** (#202). #155
  item 1 added the spread of the selected monoculture rates in 0.3.0 and updated the field table, but not
  the sentence in `meta.statistics.test`, the one in `meta.provisional`, or the README, all of which travel
  to a reader. On the published corpus 6 of 12 arcs carried the third component, and on one it was **83
  per cent of the variance** behind its q-value, so a reader reconstructing the test from the two named
  parts got a different number from the published `p_value`.
- **Four places still said a censored matrix cell holds a measured bound** (#203). It holds `NA`, settled
  on #129, and the bound travels on the arc. The README said it twice, the `--format` help once and the
  `strength_bound` field description once, which are the places a reader looks first, and two code
  comments said it to the next maintainer. The changelog's own 0.3.0 note warns that a reader of the
  matrix must handle `NA`.
- **A download could hand over a different search's network** (#189). Every output a reader takes away
  (the four download formats, the report, the rates, the gLV package, Send to Cytoscape) is looked up by
  the `job` in the request, and a request naming a search the server no longer had fell through to the
  **most recently viewed** result instead. The page refused the same id and said so, while the download did not:
  HTTP 200, the ordinary filename, and somebody else's matrix inside. Searches are pruned after twenty
  (`KEPT_JOBS`), so a tab left open while you work in another meets it without doing anything unusual. A
  request that names a search the server cannot produce is now refused, with the same words the page
  uses; naming no search at all still means the latest one, which is what that fallback is for.
- **A study with no `uploadedAt` was cached forever** (#190). The stamp was read with
  `data.get("uploadedAt", "")`, so a missing or blank one became `""`, which compares equal to itself on
  every later run: the freshness check said "current" forever and a revised study was never read again.
  The guarantee the whole cache rests on was satisfied vacuously, and for exactly the studies whose
  version nothing can establish. `null` was already safe; a missing key and a blank string now behave the
  same way, and nothing is kept for such a study.
- **A study whose `uploadedAt` is only whitespace was still cached forever**, and the version record a
  reader quotes still wrote an empty string for a study that carries no stamp at all. `or None` caught a
  missing key and `""`; `"   "` is truthy in Python and survived, which is #190 with a space in it. And
  `data_versions` is not a cache: it is what says where a network's data came from, so it now states an
  absence in words rather than as an empty string, the way the database-level version already did.
- **An answer that carries no body by definition was parsed as one.** The status guard below closed 1xx
  and 3xx; 204 and 205 are 2xx (RFC 9110 sections 15.3.5 and 15.3.6) and carry no body, so they still
  reached `json.loads`, which is the failure that guard exists to prevent.
- **A search that was still running was told it was gone.** The refusal added below covers a job the
  server cannot produce, and `status` takes two values: a reader who hit download while their own search
  was still working was told "no longer here; run it again", which sends them to repeat work already
  under way. It says it is still running instead.
- **A redirect from mGrowthDB was read as a growth curve** (#191). `_send` raised only on 4xx and 5xx, and
  `http.client` does not follow redirects as the `urllib.request` opener it replaced did, so a 3xx body,
  which is empty, reached `json.loads`. The command line has no handler for that and told the user **their
  own file** was not valid JSON, with the exit code for a user error and no status on the error. Anything
  that is not a representation now raises the client's own error, carrying its status, and it is not
  retried, since a redirect does not become a representation by asking again.
- **The About page told a reader of this build that their default derivation is the integrated form.**
  A test pins the newest entry of that log to `__version__`, so the list is read as "what your version
  does", and `__version__` does not move until the next release: leaving the reversal for the next
  version's entry meant the page contradicted `DEFAULTS["derivation"]` for everyone in between. The 0.3.0
  entry now says what 0.3.0 did in the past tense and states the reversal beside it, which keeps the rule
  that a tagged version is never reused for changed content without lying to the reader in front of it.
- **Two tests passed on the thing they were written to catch.** The one pinning that both derivations
  cite a study by the same field searched a window of source text for the first of four field names, and
  the regression it documents names two of them in that window, so it returned the same answer for the
  broken source and the fixed one; it now reads the assignment and proves it can tell them apart. The one
  named for the report and the help naming the derivation asserted `"integrated" in render_help(...)`,
  which `render_help` cannot know, since it takes no settings: both halves were properties of a static
  table. It now checks the report follows the setting in both directions.
- **The integrated form told every reader its standard error had two components, and it has had three
  since #155 item 1.** `_arc_statistics` returns `se_replicates`, `se_rate_stage` and
  `se_rate_selection`, and takes Satterthwaite degrees of freedom over whichever are present, so the
  third was being computed, published in the fields and omitted from the sentence that describes them.
  The spread of the selected monoculture rates is not a footnote: on the corpus 6 of 12 arcs carried it,
  and on one it was 83 per cent of the variance. **The claim stood in four places**, the `statistics`
  description, the `provisional` sentence, `_arc_statistics`'s own docstring and the help page and README,
  and the first two travel into `meta`, the report header, GraphML and every exported file, so a reader
  met the wrong count before meeting any document. All four now say up to three and name the component,
  and two tests hold them there: one reads the strings the deriver publishes, the other reads every
  surface that describes the test to a reader, because what let this stand for two days was fixing one
  copy and not reading the file.
- **`derive --all --live` could answer with a network derived the other way.** The daily artifact is
  accepted on its format, its schema id and its age, and none of those can see which derivation filled
  the fields: a format id moves when a **field** changes meaning, and the derivation is not a field. So a
  reader at the default would have been served 0.3.0's 12-arc integrated network in place of the 145 arcs
  their own settings produce, until the scheduled workflow re-derived. The artifact's own
  `settings.derivation` is now compared with the reader's, and an artifact from before that field existed
  is still served, since its age and schema already protect it.
- **gLV mode's own switch did not know about the fourth setting it sets.** `glv_mode_on` read three while
  `glv_mode` wrote four, so with the comparison selected the toggle still said "on" (and `aria-pressed`
  told a screen reader so) in the one state where a coefficient is *not* being fitted by the form the
  mode exists to select; pressing it then switched the mode off rather than completing it. The page's two
  messages and the caption beside the button said three settings as well, while the command line said
  four.
- **The gLV example button produced a run no package can be built from.** It set the growth rates and the
  study and inherited the rest, which worked only while the shipped derivation happened to be the
  integrated form. It presses gLV mode now, so the two cannot drift again. Its test asserted
  `derivation == DEFAULTS["derivation"]`, which is true whatever the default is, which is why it passed
  while the button broke; it asserts what the button has to achieve instead.
- **`--to-r` wrote a whole network to stdout and then died with a traceback** when the comparison could
  not give it coefficients. The guard that exists "so a run never writes a network and then refuses to
  write the files beside it" covered `--glv` and not `--to-r`, which only mattered once the default
  stopped being the form where the metric is irrelevant. The command in `derive --help` was one of the
  two that hit it.
- **gLV mode overrode a derivation the reader asked for, and that broke the decision register's own
  reproduction command.** The register prints
  `derive SMGDB00000007 --live --glv-mode --derivation <either> --steady-check` as the record of the
  measurement behind its comparison table, and says in as many words that the command was added because
  two readers had taken the table for a fabrication when it was missing. Making gLV mode set the
  derivation, in this same set of changes, made both arms of that command give the identical answer, so
  the remedy for "this looks unreproducible" was unfixed the same day it was relied on. An explicit
  `--derivation` now wins and the banner says so; without one, gLV mode still selects the integrated
  form. The flag's own default is `None`, meaning "not given", so the page and the command line still
  resolve to one default from one place.
- **`derive --help` shipped two examples the tool refuses**, and the README a third. Both gLV examples in
  the command line's own epilog used `--report-rates` and relied on the shipped derivation being the
  integrated form, so with the comparison back as the default they exit 2, as did the README's `--to-r`
  line. They press gLV mode now. The README also offered `--report-rates --no-dropout` as the command
  line equivalent of gLV mode: it sets two of the four settings the mode sets and gives a different
  network, which it now says. And `docs/LIMITATIONS.md` entry 1 still opened by calling the held rate
  "the default derivation", six lines above the paragraph added yesterday that corrects it, so a reader
  who stops at the bold line takes the rate-mismatch limitation to apply to every default network.
- **Every study lost its citation under the integrated form**, which is what gLV mode selects and what
  derived the published All artifact. `integrated.py` read `study.get("citation")`, a key mGrowthDB has
  never had, while the comparison reads `name`, so the JSON's `studies[]`, the report's "cite the studies
  behind the edges you use" block and the page's Sources all carried the accession number in place of the
  title. Today's published `all_report.txt` ends with five such lines. A test now pins the two paths to
  the same field of the same record, which is what drifted.
- **The page's help said the drop-out setting "changes nothing either way"** under the default. It governs
  most of the default network: with it the corpus gives 145 arcs over 24 organisms, without it 23 over 11,
  because 122 of those arcs are drop-out arcs. The sentence was true of the integrated form and was left
  pointing at the default when the default moved, so the one place a reader is told what that setting does
  waved them past it. It now says what it does, with the measurement, and names the form it does not
  govern.
- **Three more places still described the integrated form as the default**, found by reviewing the three
  open changes as one tree rather than one at a time. The README's gLV section had the two derivations
  swapped, so the paragraph a reader consults to learn what `carrying_capacity` and `capacity_source` mean
  described the wrong one, and `capacity_source` is empty under the default because nothing fits the
  plateau there. The README also promised `growth_rates.csv` is "in the same order" as the matrix, which
  is false for a multi-unit package and makes a positional join give a plausible, wrong simulation; the
  organism column is the join key and the claim is gone. And the help's gLV walkthrough printed a command
  line that exits 2 under the default, because the button was taught to press gLV mode and the command
  beside it was not.
- **The report did not carry what the derivation says about itself.** `meta.provisional` reached the JSON,
  GraphML and the page and never the report, which is the artifact `docs/LIMITATIONS.md` nominates as the
  one that travels with the output and the one a methods section is written from. So a reader could quote
  a derivation's limits only from a file they were not reading. The report prints it under "about this
  derivation". (The commit that added those limits said they traveled into the report header; they did
  not, and this is that claim made true.)
- **The default derivation said nothing about its own two limits**, in the sentence that travels into
  every report header, into GraphML and into a methods section. It named neither while it was the
  alternative; as the default again it reaches every reader, and 122 of the 145 arcs on the live corpus
  come from a drop-out design. `meta.provisional` now says that a drop-out arc means the removed member
  affects the target **directly or through the others**, and that a coefficient from this comparison
  carries the organism's own density as a confound, which is why gLV mode fits the row instead.
- **`docs/LIMITATIONS.md` described the other derivation**, and promised fields the shipped default never
  writes: `rate_mismatch_to_zero`, `se_rate_selection` and the `rate_unchecked` caution are on **0 of the
  default's 145 arcs**, and `partner_abundance` on 23 of 145 rather than all of them, because a drop-out
  comparison has no single partner whose level the effect is per unit of. Entries 1 and 4 say which
  derivation they are about and what the default carries instead. **The claims gate could not see that
  file at all** (`DOCS` in `checks/claims_check.py`), so the one document whose job is to name weaknesses
  was the one nothing checked; it is in the list now.
- **Five statements still called the integrated form the default**, including two in the R package's
  shipped help, which a reader meets as `?glv_matrix`, and one that contradicted itself inside a single
  sentence in `ReplicateDeriver`'s own docstring.
- **A network said the two derivations "can be read together"**, in `meta.provisional`, which travels into
  the report, GraphML and every file. They are on the same scale and they are not interchangeable: one
  gives drop-out and censored arcs and the other gives coefficients, and the sentence now says so.
- **The claims gate had no test at all**, before or after its attribution rule was rewritten here
  (pointed out reviewing #199). It has one now, covering the five shapes that matter against a tree the
  test builds rather than against today's documents, including the case the rewrite loses: an appositive,
  where the retired deriver is the subject of the claim and the shipped one sits nearer the phrase. That
  one is recorded as a known hole rather than left to be discovered, and the test fails if the previous
  attribution returns.
- **The claims gate could not express "A is the default, B is not"**. It read a phrase such as "is the
  default" as a claim about **every** deriver named within 200 characters, so the one sentence a reader
  now needs, naming both forms and their jobs, was unwritable without tripping it. A phrase is attributed
  to the **nearest** deriver mention instead. The gate caught this change's own documentation drift
  first, which is what it is for.
- **The page's Example gave an empty network** (Karoline, 2026-10-09, the day 0.3.0 was released). Two
  causes, both of them in the button rather than in the derivation.
  **It inherited whatever settings were in the form.** Pressing gLV mode and then Example ran the example
  in gLV mode, which turns drop-out communities off; pressing the gLV example and then Example ran it with
  that example's study still in the second box, so it searched one study that holds neither species.
  Either gave no interactions, and nothing on the page said why. The Example now puts **every setting back
  to its default** and says so, which is what a button that shows the tool working has to do.
  **And its two species no longer have an arc between them under the shipped default.** What those two
  hold is a drop-out comparison inside a three-member community, and the integrated form does not fit a
  row from a community of three or more, so the default derivation has nothing to report for the pair.
  The example is now the three organisms that are actually grown together, which is the smallest change
  that keeps the biology and the studies: measured live, **three arcs over three organisms against none**.
  The worked example in the README, the command line's help and the help page moved with it.
- **The release-date guard failed on every pull request from the morning after a release.** It reads
  `__version__`, finds that section in the changelog, and refuses a date earlier than the tree's newest
  commit, which is what catches a release dated before the work it contains (#155 item 8). After the
  release, `__version__` still names the version that shipped and its section is still dated, so every
  commit of the next cycle is newer than that date and the check failed on work that has nothing to do
  with it. It asks the question only while the tree is the release being prepared now, and stops once
  `## [Unreleased]` has content, which is what `RELEASING.md` says to start when work continues. A tag
  would say it exactly, but `actions/checkout` fetches none, so a tag-based check would pass on a
  developer's machine and skip in CI.

## [0.3.0] (2026-10-09)

### Upgrading
- **The default derivation is now the integrated form** (`--derivation integrated`, Karoline,
  2026-10-06): each organism's row is fitted from its whole time course rather than from a difference of
  two separately fitted growth rates divided by one partner mean. It is the form published work fits for
  this purpose, and the difference form's coefficient carries the organism's own density as a confound,
  which no number of replicates removes. The specified comparison of replicate sets is unchanged and is
  one setting away, `--derivation replicate`, and it is what a sparsely sampled study can still give: the
  integrated form needs a time course, so a study measured at two or three points now yields nothing by
  default and the page says which setting to change.
- **The network format id moves to `grownet.interaction_network/v3`** (#121, Craig's agent's trace, and
  #155 item 1). It moved twice inside this release, `/v1` to `/v2` to `/v3`, because each step added
  optional arc fields and **a field addition moves the id whether or not the id it moves from was
  released**. No release carries `/v2`; a reader still accepts it, and `grownet validate` names it. The
  rest of this entry is why the first move happened.
  Files from 0.1.x (`/v0`) and 0.2.x (`/v1`) stay valid and `grownet validate` still names the version it
  read. The id is what `published.fresh` checks before an installed copy uses the daily All network, and
  #118 added optional arc fields that an installed 0.2.0 cannot build, because it builds each arc from
  every field a document carries. Under the unchanged id that copy would have accepted the next daily
  artifact and then raised inside the All button, with the derive-live fallback never reached. With the id
  moved it reads the artifact as a format it does not know and derives live, which is what the fallback is
  for. A reader of its own is unaffected: nothing an older field means has changed, and the new fields are
  optional. Two readers are hardened with it: **every** record kind now drops a field it does not know
  rather than raising, nodes and studies as well as arcs, and any failure to read the published network
  means derive live.
- **Reinstall the R companion package** when you upgrade: `remotes::install_github("crossfeed-bio/crossfeed", subdir = "r")`.
  A 0.2.0 R package reads no organisms out of a 0.3.0 payload. Send to R now says so and names that
  command rather than reporting a successful send into an empty matrix.
- **A gLV package now states where its matrix settles**, and says plainly when it settles nowhere with
  every organism above zero. Nothing about the coefficients changed because of it; the equilibrium was
  always the solution of `A x = -r` and the reader had to work it out.

### Added
- **What the data cannot settle is listed on its own, in `docs/LIMITATIONS.md`** (Karoline on 2026-10-08:
  "if p-val computation is indefensible, we do not report p-values and comment on the weakness"). Six
  questions, each with what is not known, what grownet publishes instead of a number that would imply it
  was settled, what would settle it, and what it blocks, which is nothing in every case: the held
  monoculture rate, whether a fitted growth rate is plausible, what the absence threshold means inside a
  matrix, which partner abundance a coefficient is divided by, when a culture has reached stationary
  phase, and whether a gLV model describes these communities at all. It states the rule the rest of the
  tool already follows, that where the data cannot settle a question grownet publishes the measurement and
  names the weakness, and it is linked from the README and the help page. A seventh entry, added after
  Craig's agent read the first six, is the most general and the one with an open issue of its own: **the
  tool never establishes a mechanism.** A non-zero coefficient cannot tell a metabolite handed over from a
  pH shift, from competition for a shared resource, or from one organism sparing another a cost, and a
  perfect fit leaves that exactly where it was. It is Karoline's own reason for #71, the naming question,
  and the output already says effect rather than route: `facilitation` means the target grew more with the
  source, and nothing in a file or on the page claims a mechanism.
- **The statistics are labeled as support, and an arc says what its test assumed.** The p-value and the
  q-value decide nothing and never did: the status comes from the absence threshold and the q-value filter
  is off unless you set it. The help page now says that where the fields are described, and adds the third
  reason the p-value does not decide, which is specific to the default derivation: its null assumes the
  organism grew at its monoculture rate in the co-culture, and no growth curve in these designs measures
  whether it did. So the report prints, beside the q-value, how large an error in that rate would explain
  the arc away, and a new caution **`rate_unchecked`** marks an arc whose organism has one matched
  monoculture set in its study, where nothing checks that assumption at all. 7 of 16 live arcs carry it;
  the other 9 carry the measured lower bound instead.
- **An arc's error carries a third component: which monoculture set stage 1 was given** (#155 item 1,
  Karoline on 2026-10-08, taking Craig's agent's recommendation). The condition matcher resolves a
  monoculture set per co-culture experiment, so one organism in one study can enter two arcs with two
  different stage-1 rates: on SMGDB00000007 *Roseburia* enters one arc at 0.5091 /h and another at 0.6521,
  17 per cent apart. Each arc took its own as though the other did not exist. The spread of those selected
  rates is now a measured third variance component, `se_rate_selection`, with the spread itself in
  `rate_selection_spread` and both named in the arc's notes with the rates behind them. **It moves `se`,
  `sd`, `p_value` and the degrees of freedom only**: `strength`, the effect and the status stay as fitted,
  because the point estimate is what it is and the confidence in it was what was overstated. It needs no
  number from the reader. On the live corpus **9 of 16 arcs widen** and one loses significance at
  `q < 0.05` (3 arcs to 2); no arc changes status. It is a **lower bound** on what an arc assumes, since
  the gap each arc takes on trust is between a monoculture and a co-culture the monocultures were never
  grown in, and the notes say so. Where two arcs of one organism took nearly the same rate and still imply
  mismatches of opposite sign, the arc says that too: they cannot both be the rate being wrong, so for at
  least one the implied mismatch is growth that depends on the partner. No live arc meets that condition
  today. The spread is the **sample** standard deviation of those rates, which the field description and
  the method notes now say rather than leaving it to the choice of function (Craig's agent on #177): which
  sets a study holds and which one each arc was matched to is one realization of a matching, so they are a
  sample rather than the whole population, and the population form would be narrower by a factor of 1.41
  where two sets were selected.
- **Every growth rate is published with the doubling time it implies** (#173, Karoline on 2026-10-08).
  `ln(2) / r` in the time unit of the rate, as the appended `doubling_time` column of `growth_rates.csv`
  and beside each rate in the report. No stage of the derivation asks whether a rate is plausible: the
  guards are identifiability, model fit, growth above zero and the fit against the interaction-free null,
  and a rate's magnitude is never questioned. Of 123 live monoculture fits that pass every guard, three
  imply a doubling slower than 24 hours and all three are from one study, where `0.0147 /h` reads as a
  number and 47 hours reads as a mistake. This catches nothing automatically and is not a guard; it puts
  the fit in front of the reader who can catch it. The column is appended, so a reader parsing that file
  by column index is unaffected.
- **A censored cell of the plain adjacency matrix is `NA`, and its bound travels on the arc** (#129,
  Karoline on 2026-10-08). A pair whose only arcs are obligate or abolished has no log2 ratio, because one
  side did not grow. Such a cell used to hold +/-10 by convention, and within this release it briefly held
  the measured bound the no-growth rule puts on that side. It now holds **`NA`**: measured on the live
  corpus, 11 of the 12 bounds land inside the range of the quantified arcs and 7 below their median, so a
  bound printed in a cell sorts among the ratios rather than past them, and nothing in a CSV cell can say
  that a number is a floor rather than a measurement, which is the same objection that retired +/-10. `NA`
  is what R reads as not a number, where 0 would read as no interaction about the strongest effect in the
  set. The bound itself is unchanged and is on the arc (`strength_bound`, `bound_rule`): the report prints
  it with its rule, the page names every cell left `NA` beside the download, and `matrix.bounded_cells`
  gives the listing as data. The three censored cells whose rule bounds nothing away from zero now read
  `NA` too, where they fell through to 0. **A reader of the matrix must handle `NA`**, and a pair left at 0
  for disagreeing in sign is still 0, named as a conflict.
- **What a study holds is kept between runs and reused while its `uploadedAt` is unchanged** (#182).
  Until now every run read everything again: a corpus run sends 3738 requests (2195 bioreplicate records,
  930 series, 559 experiments, 54 studies) and a single study 153. The rule was that measurements are read
  fresh, because mGrowthDB serves only the latest version of a study; what makes keeping them safe is that
  a study's `uploadedAt` moves whenever it is revised, which **Karoline confirmed for the mGrowthDB team**:
  "uploadedAt is kept fresh", and "it's coupled to study submission". So responses go to the user's own cache
  directory (`GROWNET_CACHE` moves it, `--no-cache` keeps nothing, never inside the repository), each file
  carrying the study and the stamp it was read at; **the study record is always read live**, because it is
  the check; and a stamp that has moved drops everything kept for that study. Measured live on
  SMGDB00000007: a first run sends 153 requests and a second sends **1**, deriving the same network. The
  **command line's** report says how much was read, how much was reused, and which studies were read again
  because their stamp moved, and those two counts are now incremented under the same lock as the rest of
  the shared state, since one client serves six worker threads and `x += 1` is three steps (Craig's agent
  on #185); an undercounted reuse makes a network look fresher than it is. **The page's report does not
  carry that line yet** (#187): the page keeps the kept responses and the speed, and says nothing about
  either, which is a gap in the reporting and not in the caching. The daily All workflow is unaffected,
  since its runners keep nothing.
- **Each arc says what both sides of its comparison were inoculated at** (#81, Karoline on 2026-10-08).
  mGrowthDB's `inoculumConcentration` is empty in every experiment checked and its descriptions state a
  starting density unsystematically, so the number is taken from the first measured abundance, which the
  curves always carry. The note gives both sides and the factor between them, and says plainly when that
  factor is above 3, so a reader can see that an arc rests on a monoculture started several times denser
  than its co-culture. It is **reported and never matched on**: across the comparisons the tool makes the
  two sides agree to a median of 1.17 times and differ by more than 3 times in 6 of 39, and those six are
  a choice about how to start a co-culture rather than a confound, so putting a starting density in the
  condition key would discard measurements. On the live All network **all 12 arcs carry the note and the
  warning fires on 4 of them**, the largest being a co-culture started 7.43 times thinner than the
  monocultures it is compared with.

### Changed
- **A monoculture fit is refused for model failure rather than for the rate's sign** (#160, Karoline on
  2026-10-08, taking Craig's agent's option 2). A non-negative `A_ii` is no self-limitation: the fit
  implies no plateau and an unbounded culture, which is the direct answer to whether the model describes
  the curve. The old guard read the sign of the rate, which on SMGDB00000006's *S. thermophilus* kept the
  one replicate of three whose rate happened to land above zero while all three had fitted a **positive**
  self-limitation; because only a near-zero positive survives such a cut, the survivor is biased toward
  zero by construction, which produced a published rate of 0.0109 /h, a 64 hour doubling time for a dairy
  starter. A non-positive rate is still refused.
  Three things move on the live corpus. *S. thermophilus* loses its rate, so SMGDB00000006 yields a
  one-organism matrix rather than a pair. *A. tumefaciens*'s rate moves from 0.1022 to **0.1579 /h**,
  because two of its three replicates had fitted tiny positive self-limitations and were contributing to
  the median unnoticed. And the All network goes from 14 arcs to 12: the two lost are
  *L. delbrueckii* -> *S. thermophilus* (q 0.024, which was significant) and
  *Comamonas* -> *A. tumefaciens* in metalworking fluid (q 0.064, which was not). **A significant arc is
  withdrawn**, and that is the point rather than a cost: it rested on a rate of 0.0109 /h that only a
  sign cut on the wrong statistic had kept.

### Removed
- **The retired `BaselineDeriver` is gone** (#139). It was the placeholder grownet shipped before either
  real derivation existed: one summarized `growthRate` per culture, `log2(co / mono)` with a fixed
  deadband, no replicates, no spread, no test. It had been off the default path since #34 and reachable
  only through `--deriver`, and the seam it was built to demonstrate now holds two real derivations.
  `interactions_from_experiments`, `_strain_growth`, `DEADBAND` and the baseline's own method label go
  with it, each having had no other caller. Nothing user-facing changes: no default path and no
  documented workflow used it, and `derive SMGDB00000004 --live` gives the same network as before, to the
  byte apart from its two timestamps. What it did is recorded in `docs/METHOD_NOTES.md`, where the
  register's `[baseline]` tags say which option the first implementation took in each menu.

### Fixed
- **The release check refuses a release date that is not the day of the tag** (found while preparing
  0.3.0). A date in the past passed every check: the future-date guard does not see it, and the agreement
  guard compares the changelog with `CITATION.cff`, which have nothing to disagree about while the
  changelog says `(unreleased)` and gives no date. 0.3.0 sat in exactly that state, with `CITATION.cff`
  naming the day it was prepared, and tagged later that date would have shipped as the release date, as one
  release's date was carried into the next before. The check now asks that both files name the day the tag
  is cut, with one day of slack for a tag pushed just after UTC midnight from a tree prepared the evening
  before, and it says what to do. It is a release-day rule only: preparing a tree with an older date is
  not a problem.
- **A black-holed IPv6 address no longer costs 17 seconds on every connection** (found with the sibling
  tool foodnet on the same network, 2026-10-09). mGrowthDB publishes an AAAA and an A record, and on some
  networks the IPv6 address is a black hole: measured at KU Leuven, it never answers and the operating
  system takes **17.5 seconds** to say so, while IPv4 connects in 14 milliseconds. `getaddrinfo` returns
  IPv6 first and `http.client` walks the addresses in that order with the full timeout on each, so every
  new connection paid it, once per worker thread in a cold run. Now an unproven address family gets three
  seconds and the next family is tried as soon as it fails, and the family that answered is remembered for
  the rest of the process, so only the first connection can wait at all. **Nothing forces IPv4**: a network
  with only IPv6 is served as before, because the order is a preference and both families are still tried.
  Measured end to end on the whole corpus: a cold `derive --all --live --no-published` went from **368
  seconds to 113**, deriving a network identical apart from its timestamps. Overriding `connect()` to
  choose the address meant writing the TLS handshake out again, and it handed the certificate check the
  host rather than the tunnel target, which is the wrong name through a proxy (Craig's agent on #184).
  Nothing in grownet configures a proxy, so the branch is unreachable and nothing was ever verified
  against the wrong name; it now computes that name the way `http.client` computes it, so the only
  difference from the base class is the address choice, and a test holds the override to it.
- **Send to Cytoscape carries the parts of an arc's error, which it did not** (found by a round trip
  through Cytoscape 3.10.4, 2026-10-09). `se_replicates` and `se_rate_stage` have been in the file and in
  GraphML since 0.3.0 was being prepared, and `se_rate_selection` and `rate_selection_spread` since #155
  item 1, and none of the four reached the Cytoscape edge table: that payload names every field it sends,
  so a field added anywhere else stops there. A reader in Cytoscape could style or filter on the total
  `se` and not on which stage it came from. All four are sent now and declared as columns, so an arc with
  no value for one leaves the cell empty rather than reading as zero. The test that checks a column is not
  declared twice now reads the list from the sender rather than repeating it, which is what let this
  through: the list in the test was shorter than the list in the code and nothing compared the two.
  **That guard was still the wrong direction, and the right one found sixteen more** (Craig's agent on
  #181): comparing the test's list with the sender's cannot see a sender that is short, which is what
  happened. GraphML's key table and the Cytoscape payload both answer "what do we emit for an arc", so
  they are compared with each other, and the payload was missing the **gLV coefficient**, its error, its
  unit and its count, the fit's `r2`, null `r2` and condition number, the monoculture stage's method and
  count, the partner-abundance count, the target's capacity with its unit and count, the rule behind a
  censored arc's bound, and the derivation method. All sixteen are sent now, and `evidence` is the one
  field that travels under another name, as the interaction column Cytoscape merges parallel edges on,
  which the test checks rather than excuses. The column declaration was completed the same way: it held 18
  of the 33 numbers an arc may lack, so a network whose arcs carry no capacity arrived with no
  `target_capacity` column at all. Measured by the same round trip, the edge table goes from **47 columns
  to 64**.
- **Fifteen smaller things, from the two reviews** (#142 items 10, 14 and 15). A reader drops a field it
  does not know for **nodes and studies** as well as edges, so the 0.2.0-against-0.3.0 failure is no
  longer armed for the next release that adds one. The shipped JSON Schema and the model agreed in
  neither direction, which nothing asserted: `merged_arcs`, `strength_range`, `supporting_pairs` and
  `merged_pairs` were emitted and undeclared, and a test now closes the loop for all three record kinds.
  `grownet validate` names a key the format does not declare, which is the only place a misspelling can
  be caught now that the reader drops it. `_least_squares` scores its stage about zero, since the model
  has no intercept, and its docstring says its condition number is of the normal equations and not of the
  design, which differ by a square. A co-culture replicate refused for too few usable points says that,
  rather than the informational window note that replaced the real cause 196 times over the corpus.
  `rbridge.send`'s refusal tells the reader to run `grownet_listen()` again, which "send again" needed
  and did not say. `check_release.py` reads `r/DESCRIPTION`, which RELEASING.md calls the only signal an
  installed R copy is out of date, and runs **on every build** with no tag, in `make check` and in CI,
  instead of firing first when somebody pushes the tag. The drop-out setting says it applies to the
  comparison of replicate sets only, since the default derivation refuses a community of three or more,
  and the prefetch no longer reads those designs under the default. The one-unit-per-organism invariant
  is re-checked in `matrix.py` rather than assumed, with the comment pointing at `derive` where it is
  enforced, and `plateaus()` names a plateau it leaves out instead of dropping it on a bare `continue`.
  GraphML carries the absence rule and its threshold, the suppressed counts and the test the derivation
  ran, so an edge marked absent can be read against the `k` that marked it on the route Cytoscape uses,
  along with the fit's null R2 and the two halves of its standard error. The eight `meta` keys that said
  "a promise of the format" say what is true instead, that a current derivation writes them and their
  meaning is fixed, since a `required` list would break older artifacts. And a test asserts that the
  package's matrix CSV and `/glv.json` carry the same numbers to four significant digits, which the
  README now states, since the CSV is `.4g` and the payload is the raw float.
- **A row the package publishes is now the row that was fitted** (#142 item 7). An organism whose fit
  implies no plateau was given the measured one *after* its partners had been fitted against the fitted
  self-limitation, so the published row satisfied no equation anyone had fitted and its R2 and condition
  number described a row that was not published: on *S. thermophilus* the self term moved by 2.24 times
  the whole partner coefficient the row's claim rested on, and in the opposite direction, and the
  substitution manufactured an equilibrium in which that organism settles at twice the plateau that was
  substituted in. It was not condition-matched either: on SMGDB00000013 it gave ancestral
  *A. tumefaciens* the evolved line's plateau, 56 times the ancestral organism's own. The substitution
  now happens before the partners are fitted, from the monocultures of the co-culture's own condition, and
  `capacity_source` says where every diagonal came from, in the report, the rates CSV and the payload. The
  second pass that re-read every study's monocultures to substitute afterwards is gone, with the crawl it
  cost.
- **A lag the Baranyi fit found and the guards discarded is no longer dropped in silence** (#142 item 8).
  A lag at least half the run was discarded, which is the case where it matters most, and the fit then
  paid for the flat start by trading the rate against the self-limitation: on a seven-point curve with a
  7.97 h lag it returned a rate 31 times below the project's own estimator, a positive self-limitation, an
  R2 of 0.909 and a condition number of 13, so every published gate passed it. A lag shorter than one
  sampling interval cannot move the window and is not used either (56 of the 193 lags used were below
  1e-6 h). Both guards now say what they did, a monoculture replicate whose lag was discarded for being
  half the run is refused rather than contributing a rate, and an arc whose organism's own limitation came
  out not negative carries a note saying it has no row in any matrix and why.
- **An equilibrium is not printed from a matrix too ill-conditioned to solve** (#142 item 9). It was
  solved with no condition estimate at all, `steady.solve`'s only test being an absolute pivot below
  1e-300, and printed to four significant digits with a categorical verdict: a near-singular block
  returned a number like 1e24 and had it reported as a steady state, and a change of 0.05 percent in one
  coefficient flipped the verdict. `steady.condition_of` now measures it, nothing above 1e8 is printed,
  the reason is given instead, and where an equilibrium is printed its condition number is printed beside
  it. The fit's R2 is scored over the replicates stage 2 actually used, since a replicate the fit never
  saw could otherwise discard a whole organism, and the interaction-free null is published beside it
  (`fit_null_r2`), so a reader sees how much the partners bought: on study 7's rows, 0.542 against
  -17.825 on one and 0.956 against 0.718 on another.
- **A crash that took out a whole derivation** (#142 item 12, traced by Craig's agent on #134).
  `design` leaves a partner with no curve out of the columns, since a column of zeros would claim it was
  absent rather than unmeasured, so a replicate's rows are as wide as that replicate's own partners,
  while the pooled fallback in `two_stage` asked for the union of partners across replicates.
  `_least_squares` indexed past the short rows and raised `IndexError`, which nothing caught: the call
  sits inside the loop over every target organism in every experiment, so one organism in one experiment
  ended the run for all of them. The shape is ordinary: monocultures of A with co-cultures A+B and A+C,
  which is pairwise co-culture in a community of three. Only replicates that measured the same partners
  are pooled now, the largest such set being used and every other named in the report, because padding
  the short rows with zeros would reintroduce the claim `design` refuses and dropping a partner's column
  would claim it had no effect at all.

### Upgrading
- **The strict medium rule now decides every match, not only the capacity** (Karoline, 2026-10-07: "the
  strict medium matching (exclusion of cases with modifications e.g. mucin addition) should be applied
  everywhere where medium matching is done"). `conditions` compares the compartment records, and
  mGrowthDB states a supplement, an added sugar or a removed carbon source only in the **description**,
  which `media.identity` reads and `conditions` does not. So `conditions` alone put chemically different
  experiments under one key: on SMGDB00000014 a single `conditions` value covers twelve media, and the
  monocultures of all twelve were offered to one co-culture, to be told apart afterwards by the wording
  of their descriptions. One function, `derive.condition_key`, now answers "is this the same condition"
  for the monoculture index both derivations read, the drop-out designs and the run variants, so the rule
  cannot hold in one path and not another.
  **This removes arcs**, and that is the rule working: on the live All network 22 arcs become 14. All
  eight are SMGDB00000004's, whose co-cultures are recorded in mMCB with and without initial acetate
  while its monocultures are recorded in plain mMCB, so a comparison across them would read the acetate's
  effect as the partner's. **No arc with an adjusted p-value below 0.05 is lost** (four before, four
  after). Where a comparison is refused this way the report says so instead of reporting missing data: it
  names the medium that was measured, what it has that this experiment does not, and that an added or
  removed compound makes another environment.

### Fixed
- **`grownet validate` and the shipped JSON Schema were strict in opposite directions** (#155 item 5). A
  document with one undeclared **record** key was INVALID to `validate` and valid to the schema, where
  draft-07 reads an omitted `additionalProperties` as allowing anything; meanwhile the document **root**
  carried `additionalProperties: false`, so an undeclared top-level key was the other way round, and the
  standalone viewer, which preserves unknown top-level fields on export, could write a file the schema
  rejected. Both halves are permissive now, which is what the schema's own sentence promises. An
  undeclared key is a **note** rather than a problem: calling it a problem also skipped the
  referential-integrity pass, which runs only when there are none, so one unrecognized field turned off
  the check that catches an edge citing a study the document does not hold.
- **The decline limit did not reach the co-culture plateau** (#155 item 10). `derive.target_capacity` is
  the other place a plateau becomes a self-limitation and was the only one that did not refuse a curve
  whose peak it had long since lost: 18 live values rested on curves past the limit, several with every
  curve behind the value past it. The limit now applies there too, and the advanced setting reaches it,
  which it did not before, so one setting means one thing.
- **Smaller ones** (#155 item 14). `q_value` was rounded to six **decimal places**, so an adjusted
  p-value below 5e-7 published as exactly `0.0`, the strongest q there is, and `significance` came out
  infinite; it is six significant figures now. `published.fetch_from`'s guard covered the fetch and the
  JSON parse while the `TypeError` its own comment describes comes from `from_payload`, which sat outside
  it; the whole read is inside now. `meta.study_id` was emitted by every single-study derivation and
  declared nowhere, because the schema-agreement test covered node, edge and study and not `meta`;
  `_meta_problems` also ignored an undeclared key in silence while `_unknown_keys` called one a problem
  three lines away, and both are notes now. `derived_on` was documented as UTC and has always been the
  local date. `--glv`'s help demanded `--metric growth_rate`, which only the specified comparison needs.
  `r/README.md` quoted a `print(x)` line the R code cannot produce.
- **The release workflow published to PyPI without running the suite, the gate or the linter** (#155
  item 7). Its job graph was `check` -> `dist` -> `install` -> `pypi`, where `check` ran only
  `check_release.py` and `install` ran `grownet --help` and the smoke script. `ci.yml` does fire on a tag,
  but the two workflows are independent and nothing linked them, so a tag whose suite was red still
  reached PyPI, held back only by the optional environment approval. A version on PyPI cannot be replaced,
  which makes it the one failure in that workflow that cannot be undone. `check` now runs `ruff`,
  `checks/gate.py` and the whole suite before the tag is believed, and both the workflow's own header and
  RELEASING.md said otherwise and now say what happens.
- **The release gate could not be green and honest at the same time** (#155 item 8). With no tag it
  synthesised `v{version}` and ran the full tag check, including "CHANGELOG.md still marks {version}
  unreleased", so any tree whose in-development version was marked unreleased failed `make check`, which
  is the Keep a Changelog convention the file follows. The only green states were to leave the version at
  the last released one or to mark the next release released before it is; the tree took the second and a
  test pinned it. That check now applies only when a release is being cut. Two more holes with it: the
  date agreement read only a parenthesised date, so `## [0.3.0] - 2099-01-01` passed in silence against a
  different date in `CITATION.cff`, and two files agreeing with each other is not either being right, so
  a date in the future is now refused. The tree was wrong in exactly that way, dating the release
  2026-10-06 while every commit in it was 2026-10-07 and both files agreed; both now say 2026-10-07, and
  a test compares the release's date with the newest commit rather than only the two files with each
  other.
- **The package README described the diagonal backwards under the default** (#155 item 11). The
  off-diagonal prose was branched by derivation and the diagonal's was not, so a package from the
  derivation that ships said `K_i` is "the plateau of the curves that reached stationary phase" when on
  that path `A_ii` is a parameter of the fit and `K_i = -r_i / A_ii` is derived from it, the opposite
  direction, while `capacity_source` in the same zip said "fitted from the monoculture time courses". The
  diagonal now has its own words per derivation. The promised SELF-LIMITATION FITTED AT A CO-CULTURE
  PLATEAU section was also unreachable on that path, because it is filled from `edge.target_capacity`
  which the integrated derivation never sets, so the one diagonal in a package that is **not** a fit
  appeared in no section at all; a DIAGONALS THAT ARE NOT A FIT section now names those organisms and
  what was put in place of the plateau their fit did not imply.
- **Shipped text quoted counts of mGrowthDB, and the counts were wrong** (#155 item 6). The help and the
  README said the medium names alone give 15 media and the rule gives 60, or 58 with the alias table.
  Measured over all 559 live experiments with the table on, which is the only way the tool runs, it is 13
  and 57; the older figures predate the alias table and the rule that a stated amount of zero is not an
  addition. Karoline's rule is that shipped text quotes no corpus numbers, since they depend on the state
  of a database grownet does not control, so both passages now describe the rule without counting.
- **The README and the register described machinery that had been deleted** (#155 item 12). The README
  still said an arc carries the spread over "leaving out each monoculture replicate in turn" and "the
  share of that spread" from the monoculture stage, which is the sentence the register formally withdrew
  as not a share of anything; it now describes the two disjoint designs that replaced it. It headed the
  integrated form "A second derivation" while calling it the default elsewhere, and gave the comparison's
  formula as what `--glv` writes for every derivation. `docs/METHOD_NOTES.md`'s live figures are
  re-measured: 14 arcs, 9 at p < 0.05, 4 at q < 0.05, the monoculture stage dominating on 8 of the 13
  arcs that have both halves, and a median `fit_r2` of 0.917 with none failing to beat its
  interaction-free null.
- **A GraphML exported from the page carried none of the graph-level attributes** (#155 item 4). The
  Python writer reads them from a nested `meta`: `absence_rule` is `meta.absence.rule`, `absence_count`
  is `meta.absence.absent`, `statistics_test` is `meta.statistics.test`, and `hidden` is the counts
  joined. The viewer looked up the flat names directly on `meta`, so four came back empty and `hidden`
  was written as `[object Object]`. The purpose of adding them was that an absent arc can be read against
  the `k` that marked it on the route Cytoscape uses, and on that route there was no `k`. The viewer now
  resolves them the same way, and writes a double whose value is whole as a float, so 2.4e8 is
  `240000000.0` on both routes rather than differing by a formatting artifact.
  The test that keeps the two writers equal built its network with no `meta` and a record carrying none
  of the fitted fields, so every key this release added was skipped on both sides and the equality held
  vacuously. Its fixture now carries a full `meta` and all thirty-odd arc fields, which is what found the
  two float cases above.
- **A stated amount of zero was read as something added** (#155 item 3). SMGDB00000014 states its
  no-fatty-acid arms as "0% linoleic acid" and "0% oleic acid", and the amount pattern matched the stated
  zero, so each became a medium with a compound added at zero: two media that do not exist. Neither was
  plain minimal medium and neither matched the other, though all three are the same plain medium. An
  addition now needs an amount above zero, in `media.alterations` and in `key_from_label`, which reverses
  the label it writes, so a network derived before the rule reads as the plain medium rather than
  disagreeing with a freshly derived one. SMGDB00000014 holds 11 media instead of 12, and the four
  experiments of the two phantom arms join plain minimal medium.
  **This changes no number in today's corpus**: the growth rates and all three interaction matrices of
  the live All package are byte-identical before and after, and SMGDB00000014's three arcs are unchanged.
  The item recorded an 18.4-fold change to *A. tumefaciens*'s carrying capacity, which was true when it
  was written and is not now: keying capacities by medium and the strict rule moved that capacity to
  metalworking fluid, a medium these arms were never in.
- **The `conditions_unverified` caution had silently stopped firing on drop-out arcs.** `_variants` keys
  by community and condition, and `_dropout` looked that key up with one element fewer than it was built
  with, so the lookup missed every time and defaulted to "one variant": two full communities told apart
  only by their descriptions were no longer cautioned. Found by a test while the key gained the medium.
- **A capacity came from one medium on one derivation and from several on the default** (#155 item 2).
  Karoline's decision of 2026-10-07, that plateaus are not pooled across media because a capacity sits
  beside off-diagonals measured in one of them, was in force for `--derivation replicate` and not for the
  derivation that ships: `integrated.fitted_rates` collected the media for reporting and then took the
  median over every fitted row whatever the medium, with `capacity_medium` unset and
  `capacity_curves_left_out` empty. Fitted plateaus are now collected per medium, the medium with the
  most rows is published and named, and the rest are named in `capacity_curves_left_out` instead of
  pooled in. On the live All network four of the eight carrying capacities move: *Roseburia intestinalis*
  by 5.3 times (3.835e9 to 7.268e8 Cells/mL), *Blautia hydrogenotrophica* by 2.5, *Comamonas
  testosteroni* by 1.8 and *Agrobacterium tumefaciens* by 1.02, and each gLV diagonal, which is `-r/K`,
  moves with its capacity. The rate itself is still the median over every row, since a rate is a property
  of the organism in each medium it was measured in and only the plateau is the one the matrix sits on.
- **`capacity_fall_from_peak` was always empty under the default derivation** (#155 item 2). The fall was
  measured inside the measured-plateau rule and discarded, while the help said it is published beside the
  capacity. It now travels with the plateau, and the help says it is empty where the capacity is the
  plateau a fit implies rather than one a curve reached, since there no curve exists whose fall could be
  measured. The help also says the lag column is empty under the default derivation, whose model has no
  lag term at all.
- **The gLV example rested on a monoculture fit that had failed, and the help called it the only one of
  its kind** (#155 item 13). The example moved from SMGDB00000006 to SMGDB00000002. Of the yoghurt pair's
  three *S. thermophilus* monoculture replicates two were refused for a negative rate and the third was
  kept at 0.0109 /h, a 64 hour doubling time for a dairy starter, while all three fitted a **positive**
  self-limitation and so failed in the same way; its carrying capacity had to be taken from one measured
  curve; and the package's steady state inverted the co-culture it was fitted from by about 90 times. The
  claim that it was "the only package in the database whose matrix settles with every organism above
  zero" was false: of the five studies that yield a package of two organisms or more, three settle. The
  new example's rates are each the median of three monoculture replicates that were all kept and all
  fitted a negative self-limitation, and its steady state puts both organisms below their own monoculture
  plateaus in the order the co-culture measured. The walkthrough now ends by holding the simulated steady
  state against that co-culture, which is the step that catches a package settling where the data never
  was, and the shipped text no longer claims the example is unique.
- **`growth_rates.csv` counted fitted rows under `replicates`** (#155 item 13). The column has meant
  monoculture replicates since 0.2.0, where it was right because the only derivation compared replicate
  sets. The integrated form merges fitted rows instead, and its row count went into that column, so a
  rate resting on three monocultures read as resting on one culture and a rate resting on one read the
  same way. It now holds the replicates the rate stage fitted, `capacity_curves` holds the curves behind
  the capacity on the same basis, and the row count stays in the text report, which already named it
  "fitted row(s)". The package README and the recorded rate rule no longer say "median over replicates"
  of a derivation that takes a median of medians.

### Added
- **What a gLV model assumes, stated where a reader meets the parameters** (Karoline, 2026-10-07). Two
  assumptions belong to the form rather than to the fit: every coefficient is constant in time, which a
  batch culture does not satisfy because the medium is consumed and metabolites accumulate, so an effect
  can change in size and in sign along the growth curve; and interactions are pairwise and add up, so a
  higher-order interaction, where a third organism changes how the first two affect each other, has no
  term in the model. The help has a section of its own, "What a gLV model assumes", ahead of the
  walkthrough; the package README has "WHAT THIS MODEL ASSUMES"; and the payload carries both as data
  under `caveats.model_assumptions`, so the zip and the R object say it without the page. Modeling a
  coefficient that varies with time or with the community stays out of scope; `docs/METHOD_NOTES.md`
  records the design that answers it instead.

- **Every fitted arc now says how large a rate mismatch would explain it away, and how much of the course
  it rests on** (Karoline, 2026-10-07). The monoculture rate is held fixed while the partners are fitted,
  so the arc is the only parameter left to absorb a difference between the rate an organism had alone and
  the rate it had beside its partner, and no growth curve measures that difference. `rate_mismatch_to_zero`
  is the fractional change in that rate which would drive the arc's coefficient to zero, exactly and
  signed, from the derivatives the fit already computes: an arc at 0.5 survives a 50 per cent error in the
  rate, an arc at 0.04 does not survive 4 per cent. Checked against a simulation with a known mismatch
  planted in it, where it recovers 0.1109 against the true 0.1111.
- **A `window_partial` caution, and the share of the course a fit covers** (Karoline, 2026-10-07: "the
  effect 1 organism has on another can change along the growth curve. this is not something we treat here,
  but something we can warn about"). The integrated model has no lag term and no death term, so the rows
  start where growth starts and stop at the end of the plateau after the maximum: a course measured well
  past its peak is fitted on the early part of itself, and grownet fits one constant coefficient per arc,
  so an effect that changes along the curve is reported as whatever it was inside the window.
  `fit_window_share` is the fraction of the measured span the rows cover, a note names both spans, and an
  arc below half carries the caution. On SMGDB00000002 both arcs between *Roseburia intestinalis* and
  *Bacteroides thetaiotaomicron* are fitted on 0 to 32 of 120 measured hours and now say so.
- **A gLV example button, and the steps to simulate it** (Karoline, 2026-10-07). Beside All, **gLV
  example** fills both boxes and the one setting a package cannot be built without, and runs the search.
  The study it picks was chosen by running every study that yields a package: SMGDB00000006, two
  organisms in one abundance unit, both with a fitted rate and a plateau, and the only package in the
  database whose matrix settles with every organism above zero. The help has a section of its own, "The
  gLV example, step by step", which installs miaSim, listens in R, prints the matrix and the equilibrium,
  runs `simulateGLV` deterministically and says what to expect, with the numbers this search gives today
  and a note that mGrowthDB changes. The route above it stays generic; only the numbers are the
  example's.

### Changed
- **The gLV package states the formula its own derivation fitted** (#142 item 6). `README.txt` inside the
  package, the payload's `caveats.coefficients`, the R package's printout and its `glv_matrix`
  documentation, the help's gLV section and the About page's 0.3.0 entry all said an off-diagonal cell is
  `(r_with - r_without) / x_j` over a rate window, which is the comparison's formula and not what the
  integrated form fits: there a cell is a parameter of the fit of the whole row,
  `ln(x_i(T) / x_i(0)) = r_i T + sum_j A[i][j] integral(x_j dt)`. The package text now follows the
  derivation that made it, `caveats.derivation` names it, the R package prints the package's own sentence
  rather than one of its own, and the static R documentation gives both. The About page also no longer
  calls the integrated form a second derivation in Advanced settings: it is the default, and the setting
  switches to the comparison.
- **A network says what test its own derivation ran, not what the specified comparison runs** (#142
  items 5 and 11). `meta.statistics` and `meta.provisional` were module constants copied into every
  network, so a file derived by the integrated form claimed Welch's two-sided t-test on per-replicate
  log2 values and a comparison of replicate sets, neither of which that form does, and the claim
  traveled into the JSON, GraphML, the Cytoscape legend, the page, the report and the daily artifact. A
  derivation now states both, as it already states its `name` and its `method`, and `output_meta` reads
  them from the derivation that made the records. The ten other places a reader meets the claim say which
  derivation runs Welch: the arc glossary, the help's statistics section, the correction setting on the
  page and the command line, the Cytoscape legend, `model.py`'s own documentation of `p_value`, the
  standalone viewer and the README. `checks/claims_check.py` holds it as a retired claim, so text that
  says an edge carries Welch's test without naming the derivation fails the build.
  **And the reason it survived twelve commits is fixed too:** every page, command-line, report, export and
  threshold test asked for `derivation=replicate`, because the double they share measures two points per
  set, so the derivation that produces the daily artifact and every default user's file was covered end to
  end nowhere. `tests/test_default_end_to_end.py` serves simulated gLV time courses, runs the page's own
  `run_query` with nothing overridden, and asserts both halves: the search gives arcs, and the report, the
  page, the GraphML and `meta` all describe the derivation that made them.
- **A fitted rate, plateau and diagonal are the median of every row behind them, not the first one**
  (#142 item 4). `integrated.fitted_rates` kept the first row it met per organism, so an organism's rate,
  the plateau its fit implies, the diagonal `-r/K`, the printed equilibrium and the chemostat prediction
  were all "whichever arc the loop reached first". Every row is now merged by the median, which is the
  rule register item 14 sets for arcs and `derive.merge_rates` follows for the measured parameters, with
  each study's own median beside it, the studies sorted and unioned, and a rate in another time unit or a
  plateau in another abundance unit named rather than converted. Measured live by feeding the rows in both
  orders: the published rate differed by up to 1.42 times (*C. testosteroni* on SMGDB00000014) and the
  plateau by up to 1.2 times, while on SMGDB00000004 and 6 the rows agree and the defect was invisible.
  The count beside a fitted rate also says what it counts now, "2 fitted row(s)" rather than a number of
  monoculture replicates the fitting path never had.
- **The integrated form fits each organism's row from the monocultures of its own condition, and its
  statistics carry both stages' error** (#142 items 1 and 2). Two fixes to the derivation that is now the
  default. Stage 1 used to be every monoculture replicate of the organism anywhere in the study: it now
  follows the rule settled on #47, identical recorded conditions and the same description apart from a run
  number, through the same two functions the specified comparison uses, so both derivations compare like
  with like. On SMGDB00000014 the arc at 0.75 percent linoleic acid is gone, refused by the R2 gate that
  it had passed only because stage 1 handed it a rate from the conditions where the organism does grow;
  the TBHQ arc's coefficient nearly doubles and its reverse direction becomes identifiable. On
  SMGDB00000007 five arcs become six and every coefficient moves, the largest by 3.2 times. And `sd`,
  `se`, `p_value`, `q_value` and the absence threshold used to be computed from the co-culture replicates
  alone, so the monoculture stage was treated as exact in the one place that decides which arcs reach a
  file: that stage is now resampled over its own replicates, each co-culture replicate carries the exact
  derivative of its coefficient with respect to the stage's two numbers, and the two variances are added.
  Both halves are published (`se_replicates`, `se_rate_stage`, `rate_stage_method`, `rate_stage_n`), and
  `coefficient_sd` and `coefficient_sd_from_rate_stage` now mean what they say, on disjoint designs.
  Measured over the six studies that give arcs: 20 arcs become 17, p < 0.05 goes from 12 to 9, q < 0.05
  from 8 to 5, the largest sd grows 8.3 times, and on 5 of the 17 the monoculture stage contributes more
  of the variance than the co-culture replicates do.
- **What counts as one medium is a rule now, and it decides every medium comparison** (Karoline,
  2026-10-07, closing the open decision on #141 and then: "foodnet's strict medium rule should be applied
  in general in case someone specifies it in the 2nd search box (because such changes alter
  interactions)"). mGrowthDB names a medium per compartment and states an added sugar, a removed carbon
  source or a supplement only in the experiment's description, so a medium's identity (`grownet.media`) is
  its compartments' names without case, punctuation or a parenthesized abbreviation, plus every alteration
  the description states with its amount, plus the atmosphere where one is recorded. Over the whole
  database the names alone give 15 media and this rule gives 60, or 58 once the alias table below merges
  the two names it merges. Four things follow. **A carrying capacity
  comes from one medium**, the one with the most certified curves, named in `capacity_medium`, with every
  other medium's plateaus named rather than pooled in, which is the decision itself: a diagonal sits
  beside off-diagonals measured in one environment. **Every arc records the medium it was measured in**
  with its alterations, so SMGDB00000014's twelve chemistries no longer all read "Minimal medium (MM)".
  **A gLV package is scored against a chemostat only when the two media are the same by this rule**, which
  replaces a subset rule over the names' words that was not transitive and that matched a two-compartment
  design to one of its own compartments; where two studies spell one medium differently the report now
  says the names differ and names the word, instead of asserting that the environments do. Two live names
  do disagree with the others rather than being less complete, SMGDB00000001's "Anerobe" and
  SMGDB00000005's bare "Wilkins-Chalgren", and keying alone took the chemostat validation from 2 scored to
  1, so those two are merged by a **hand-curated alias table** (`grownet.media.WORD_ALIASES` and
  `NAME_ALIASES`, Karoline's call of 2026-10-07) rather than by a looser match, which would also merge
  names differing by a digit. It is the one place the tool calls two names that disagree one medium, so it
  is never silent: a chemostat scored across an alias says which entry did it, a capacity whose curves
  were recorded under several spellings names them all, and the label a reader sees is always what the
  study wrote. **The second
  box** still matches a medium as text, because mGrowthDB's names are prose, but says how many media one
  word reached, and the monocultures it keeps alongside a named comparison must now share the medium and
  not only the recorded conditions. The rule is foodnet's, the sister tool's, with one adaptation: foodnet
  also reads "+X" in an experiment's **name**, which is safe for a tool that reads monocultures and is not
  for grownet, where `At+Ct` and `LB+STneg` name community members and would have split two studies into
  media that do not exist.
- **A carrying capacity says how far its curves fell from their peak, and the worst of them are refused**
  (Karoline, 2026-10-07, closing the open decision on #141). `reached_stationary` certifies a culture that
  grew, reached a peak and then declined, because it has stopped growing, and the plateau recorded for it
  is that peak. Measured over all 1,331 per-strain batch curves in the database, 443 certify and 417 of
  them end more than 10 percent below their peak, the median one at a third of its peak, so a decline is
  the ordinary shape of a batch culture and refusing every declining curve would leave 20 of the 29
  organism-study pairs that have a capacity with none. The tail is a different matter: one certified curve
  hands over a peak 82 million times its last value. So the peak stays, the fall is published beside it in
  the report, in `growth_rates.csv` (`capacity_fall_from_peak`) and in the gLV payload, and a curve that
  fell further than the new **Carrying capacity decline limit** gives no capacity and is named with the
  others that gave none. The limit is an advanced setting and `--capacity-max-fall F`, 10 by default,
  which reads as "the culture still holds a tenth of its peak at the last measurement"; 0 keeps every
  certified plateau, as 0.2.0 did.
- **Send to R and `/glv.json` carry the same numbers as the zip** (#120): the payload is
  `grownet.glv/v1`, with `matrices`, one per abundance unit, holding fitted coefficients, the rates with
  the estimator, the lag and the carrying capacity beside each, and every caveat as a field: the cells
  from a comparison where one side did not grow, the pairs left at 0 for disagreeing in sign, the
  organisms and effects that could not be fitted, the media, the drop-out count and the standing note
  that a fit can have no bounded state. The R package reads v1 and still reads v0, says which kind it
  holds, and gained `unit =` on `glv_matrix()`, `glv_rates()`, `as_miasim()` and `glv_scale()` for the
  organisms counted in another unit; `glv_scale()` now warns when it is called on fitted coefficients,
  since their units already match the diagonal and scaling hides an unbounded fit rather than settling
  it. `glv_write()` writes one matrix per unit and anything the payload carried beside the numbers, such
  as the steady-state check. The page, the help and both READMEs say one thing rather than two, and the
  effect-size README that only this route still used is gone.
- **An organism with no certified monoculture plateau is fitted at its co-culture plateau** (#124 item 2,
  Karoline's "complete #124" of 2026-10-06), rather than left out of the package. The balance is the one
  #123 introduced for an organism that grows only with a partner, `0 = r_i + A_ii x_i + sum_j A_ij x_j` at
  its plateau, with every abundance measured; where it comes out at or above zero, which means the
  partners suppress the organism harder than its own rate, the organism is still named instead. Measured:
  SMGDB00000004's package now holds all three of its organisms and five fitted cells rather than two
  organisms and one, because B. hydrogenotrophica never settles alone in that study. **Each matrix also
  names the media its own arcs came from** (item 5), which keeps media together in one matrix per unit
  rather than fragmenting the corpus into one matrix per medium, since the second box already holds a
  search to one environment.
- **A censored cell of the plain adjacency matrix holds a measured bound, not the stated +/-10** (#129,
  Karoline's decision of 2026-10-06: "go with the bound in #129 following your recommendation"). A pair is
  censored because the no-growth rule judged one side not to have grown, and that rule bounds that side's
  own metric: at most its factor (1.5 by default) over its own measured start, which bounds the cell from
  below for an obligate pair and from above for an abolished one. The arc carries the bound and the rule
  behind it (`strength_bound`, `bound_rule`), the report prints both, and the gLV payload lists the
  bounded cells beside the conventional ones a network derived earlier still has. Where the rule bounds
  nothing away from zero, which happens with the area under the curve because a culture that did not grow
  still carries the area of its own inoculum, the cell stays 0 and says which growth property bounds it
  tightly. Measured on SMGDB00000013: with the growth rate the seven censored arcs come out between +4.4
  and +5.9 log2, in place of a flat +10, which as a log2 mean claimed a thousandfold effect.
- **Every cell of the gLV package comes from absolute rates, and an obligate pair is a measurement**
  (#123, her decision of 2026-10-06 after asking "Do we keep obligates despite the lack of a floor? If
  not, how can we keep them?"). The formula she settled is the same number written as a difference,
  `A_ij = (r_with - r_without) / x_j`, and that form is defined where the ratio is not: an obligate pair
  measured 0 without the actor and an abolished one 0 with it, so **the floor and the stated extreme are
  both gone from the package**, and such a cell enters the median of its pair like any other measurement.
  An organism that grows only with a partner now gets a whole row: `r_i = 0` by measurement, and its
  self-limitation fitted at the plateau it reaches beside that partner, `0 = A_ii x_i + sum_j A_ij x_j`
  there. Both rates behind every arc, and the target's own plateau in the co-culture, travel on the arc,
  in the schema, in GraphML, in the Cytoscape style and in the report, so every cell can be rebuilt by
  hand. A cell also no longer mixes sources: it used one experiment's ratio with a rate averaged over
  every study, and now both rates come from the same comparison. A network saved before this change
  carries no absolute rates and still converts through the ratio, with the README naming those cells.
  Measured: on SMGDB00000013 four censored pairs become measurements and one of them enters the matrix;
  on the whole corpus the cells move by up to a third and the chemostat check stays in the same range
  (1.6 and 3.2 times the observed steady state of SMGDB00000005's control).
- **The gLV package holds fitted coefficients, one matrix per abundance unit** (#119, Karoline's decision
  on #116). The diagonal is `A[i][i] = -r_i / K_i` with K the monoculture carrying capacity, and an
  off-diagonal cell is `A[i][j] = r_i (2^L - 1) / x_j` with L the log2 ratio of i's growth rate with j
  over without it and x_j the partner's abundance over i's growth window, so every cell is a per-capita
  effect in 1/(time x abundance). No convention is left in the package: no -1 diagonal, no +/-10, and
  nothing to scale. The zip holds one `interaction_matrix.<unit>.csv` per abundance unit, since a cell
  mass conversion would have to be invented while the dynamics are the same in any unit, and the README
  names every organism and effect that could not be fitted and why. An obligate or abolished pair takes a
  derived floor, the largest magnitude measured in the same run, rather than a stated extreme.
  A package therefore needs the comparison to be on the growth rate: **gLV mode now also sets the growth
  property to `growth_rate`**, `--glv` says which setting to change when it cannot convert, and the page
  says the same instead of failing. The rate estimator stays the reader's own setting, easylinear by
  default (Karoline, 2026-10-06: "use the lag from Baranyi and easylinear since it works better (users can
  always enforce Baranyi in the advanced options)"), and **the lag is always the Baranyi fit's**, the only
  estimator that has one, with `growth_rates.csv` naming both in `method` and `lag_method`. Measured on
  #116: every cell of a row carries the factor r_i, so the estimator sets how fast a simulation moves and
  nothing about where it settles. The plain adjacency matrix
  (`--format matrix`) is unchanged, and so is Send to R, which carries the effect-size matrix until the
  conversion reaches it (#120). Checked live: the converted matrix of SMGDB00000004 and of the whole
  corpus simulates in miaSim with no scaling and settles exactly at the solution of `A x = -r`.

### Added
- **A second derivation, from the whole time course** (#127, Karoline's "OK for 3, as an advanced option"
  of 2026-10-06). `--derivation integrated`, or Derivation in Advanced settings, fits each organism's row
  instead of comparing replicate sets: `ln(x_i(T)/x_i(0)) = r_i T + sum_j A_ij integral(x_j dt)` is linear
  in the parameters, so one least-squares fit per organism gives its rate, its own limitation and every
  partner's coefficient at once, with no growth property, no log2 ratio, no plateau to certify and no
  partner abundance to divide by. The monocultures identify `r_i` and `A_ii` and are held fixed while the
  co-cultures give the partners, since inside one experiment those columns rise too nearly together. The
  model has no lag term and no death term, so the rows start where growth starts (the Baranyi lag of #118)
  and stop where it ends (the plateau rule of register item 29). Every arc carries the coefficient, the
  residual and the condition number of its fit, and the growth rates and capacities of such a run come
  from the same fit, the capacity being the plateau it implies. A row the design cannot identify, and a
  community of three or more members, are reported rather than derived. The default derivation is
  unchanged. Measured on SMGDB00000007 against the steady state of SMGDB00000005's control: the integrated
  fit lands all three organisms at 0.41, 0.73 and 2.69 times the observed abundance, where the specified
  comparison gives 1.60 and 3.26 and fits B. hydrogenotrophica to wash out although the chemostat holds
  it; its implied plateaus (8.9e8, 1.2e9, 8.6e8 cells/mL) sit within about 15 percent of the measured
  ones, which never enter the fit.
- **The page says before the download when a package will hold several matrices** (#130, Karoline's
  decision of 2026-10-06 on the unit question): how many matrices, which abundance units, and that no
  effect between them was measured, since organisms counted differently were never grown together. No
  conversion between units is applied, by her decision, and the result section's text about the package
  now describes the fitted coefficients it holds rather than the convention it used to.
- **A gLV package can be scored against mGrowthDB's chemostat steady states** (#125, from Karoline's
  suggestion of 2026-10-06 and her go-ahead on the shortlist of #124). A continuous culture satisfies
  `A x = -(r - D)` at steady state with the dilution rate it records, and those numbers were never used to
  fit the parameters, so they test them. **Check against chemostat steady states** in Advanced settings,
  or `--steady-check`, puts predicted against observed per organism into the report and into the package
  as `steady_state_check.txt`, and names every chemostat it could not use with the reason: no dilution
  rate recorded, a perturbed run, another abundance unit, another medium, or no organism in common. It
  only reports: no coefficient or rate changes because of it. Off by default, since it reads the curves of
  chemostats a search does not otherwise need. Measured live on SMGDB00000007's package: against
  SMGDB00000005's `A8 control`, B. thetaiotaomicron lands at 1.6 times the observed steady state and
  R. intestinalis at 3.2, while B. hydrogenotrophica is fitted to wash out where the chemostat holds it;
  against SMGDB00000011's six-member run, 10 and 30 times, with the three organisms the package does not
  hold named as not scored.
- **Smaller things that came with the above**, each with its own setting or column: the rate estimator a
  reader chooses now reports the Baranyi lag beside it whichever one produced the rate, and
  `growth_rates.csv` names both (`method` and `lag_method`); gLV mode sets three settings rather than two,
  adding the growth property it needs; `--steady-check` and `--derivation` join the command line, matching
  the page's two new Advanced settings; the report prints both rates behind every arc, the partner
  abundance it divides by, the bound behind a censored cell, and the condition number and residual of a
  fitted row, so every number in a package can be rebuilt from it by hand.
- **The quantities a fitted gLV coefficient is made of, measured and reported** (#118, from Karoline's
  decision on #116). Every growth rate now travels with the estimator that produced it, the lag the
  Baranyi fit estimated, and the organism's monoculture carrying capacity: the plateau of its curves,
  taken only from curves certified to have reached stationary phase, in the abundance unit they were
  measured in and never converted, with every curve that gave no capacity named and why. Each biculture
  arc carries `partner_abundance`, the actor's own abundance in the co-cultures averaged over the window
  the target's growth rate was fitted in, with its unit and the replicates behind it. They are in
  `growth_rates.csv` (five new columns), in the network's meta, in the gLV payload and package, in the
  report, in GraphML, in the Cytoscape style and in the help. The matrix and the package still hold
  effect sizes and the convention on the diagonal: these numbers are reported, not yet applied. On study
  7 all eight monoculture curves of each of the three organisms are certified stationary, giving
  K of 1.05e9, 1.18e9 and 9.16e8 Cells/mL.

## [0.2.0] (2026-10-04)

### Added
- **The About page logs what each release brought**, a few lines each, newest first, with the changelog
  linked for the full record (Karoline, 2026-10-04). A test requires the newest entry to name the current
  version, so a release cannot forget its line.
- CI builds and checks the R companion package on every push (`R CMD check`, the `r-package` job, #112),
  with R and its two dependencies from Ubuntu's own packages, so no third-party action is added and
  nothing is compiled.
- **An R companion package and Send to R** (Karoline, 2026-10-03): the result section's gLV control is one
  drop-down, Download (.zip) or Send to R, and the R package in `r/` receives the parameters over a local
  port (`grownet_listen()`), or fetches them from the page (`grownet_glv(url)`) when no port can be opened.
  `grownet derive --report-rates --to-r` does the same from the command line, with `--r-port`. The package
  installs with `remotes::install_github("crossfeed-bio/crossfeed", subdir = "r")`, needs only jsonlite
  (the listener uses base R sockets), and assumes no simulator: `as_miasim()` shapes the arguments
  `miaSim::simulateGLV` takes, and miaSim stays a suggested package.
  **The caveats travel as data, not as a README to be read first**, which was her open question: the
  payload (`grownet.glv/v0`, served at `/glv.json`) carries which cells hold the stated extreme, which
  pairs were left at 0 for disagreeing in sign, which organisms have no growth rate, the absence threshold
  and grownet's own README text. In R the object prints them every time, `glv_matrix()` warns and names
  the placeholder cells (with `placeholders = "na"` or `"zero"` to convert them), and `as_miasim()` stops
  when an organism has no growth rate.
- **Get gLV parameters** in the result section, with the rates (`--glv FILE`): a zip holding
  `interaction_matrix.csv` (the matrix with -1 on the diagonal, by convention, for self-limitation),
  `growth_rates.csv` in the same order, and a `README.txt` that states the conventions, names any pair left
  at 0 for disagreeing in sign, and names every organism without a rate. The README says plainly that a
  cell is an effect size, not a fitted gLV coefficient, which is a per-capita effect in absolute units
  (Karoline, 2026-10-03).
- **The adjacency matrix as an export format** (`--format matrix`, the page's format menu): the network as
  a square CSV table, a cell holding the log2 mean of the comparison, so `A[i][j]` is the effect of j on i
  (rows affected, columns the actor). Each organism appears once, so arcs of one pair are merged across
  conditions and studies by their median; a pair whose arcs disagree in sign is left at 0; an empty cell
  and an arc below the absence threshold are 0. An obligate interaction carries +10 and an abolished one
  -10 (Karoline, 2026-10-03: "obligate and abolished arcs need to carry numbers reflecting the strong
  effect, how about 10 with the appropriate sign?"): neither has a log2 ratio, because one side did not
  grow at all, so the number is a stated extreme, named cell by cell in the gLV README, and it never enters
  the median of the arcs that do have a ratio. The diagonal is 0 here, and -1 in the gLV package.
- **Report growth rates**, an advanced setting (`--report-rates`) that the gLV mode button turns on, off
  by default: every
  organism in the network also gets its maximum specific growth rate in monoculture, by the chosen rate
  method, the median over the replicates and studies that have one, with each study's own median beside it
  in `meta.growth_rates`. Batch monocultures only (in a chemostat the rate is the dilution rate, and a rate
  from a co-culture is growth with a partner). The rates download as their own CSV (`--rates FILE`), and an
  organism whose curves give no rate is named on the page and in the report, never given a substitute.
- **A second input box: media, experiments or studies** (Karoline, 2026-10-04, weakening her stance against
  environment filtering now that gLV parameters are exported: "it's one thing to export a network of known
  interactions and another to do a gLV simulation"). Optional, beside the species box, with its own
  examples. A medium is matched as text, case-insensitively, against the medium name mGrowthDB records on
  the experiment's compartments, its description and its name, so one word finds the four spellings of
  Wilkins-Chalgren in the database; an id picks one study (SMGDB...) or one experiment (EMGDB...), and
  naming a comparison keeps the monocultures it is made against, which the report lists. On the command
  line it is `--conditions NAME ...`. **"Only these studies" has left Advanced settings**: a study id typed
  in the box does its job, and the study argument of a `--species` search still works.
- **Every arc records its `medium`**, the growth medium the comparison ran in, in the neutral format, in
  GraphML, in what Cytoscape receives and in the report. The schema gained the optional field. Nothing
  about the method changed: a comparison never mixed media, because the medium is part of the conditions
  two replicate sets must share.
- The gLV package and the R object **name the media their numbers come from**, and say in capitals when
  there is more than one, since a simulation is of one environment: the All network's package reports six.
- `glv_scale()` in the R package, and a line in the gLV README and the help: the cells are often stronger
  than the -1 on the diagonal, and a simulation run on them unchanged can grow without bound and come back
  as NA. Measured on SMGDB00000004, where the unscaled matrix diverges and the scaled one settles.
  **The factor is a free parameter, not a calibration** (Craig, reviewing 0.2.0): nothing in the growth
  data fixes the scale, so whoever simulates chooses it, and that choice, not the measurements, sets where
  the simulation settles. Report the factor you used with any result that depends on it.
- Filter on adjusted p-value (`--max-adjusted-p Q`), an advanced setting off by default (register item
  31): interactions whose adjusted p-value is above the threshold (0.05 unless another is given) are left
  out and counted (`meta.hidden.not_significant`, `meta.statistics.filter`); absent and undetermined arcs
  stay; arcs without a p-value (obligate, abolished, a single replicate) are kept with the caution
  `untested`; merging uses only the arcs that passed. The help says why it is off by default: with two or
  three replicates the test misses many real effects, and an adjusted p-value depends on the other
  comparisons in the same search.
- The help page explains how an interaction is decided, in a section of its own: the effect, the absence
  threshold, Welch's t-test, the multiple testing correction and its family (every comparison of one
  search), which arcs have no test, and the filter. The correction setting's text on the page, in the help
  and on the command line says what the correction runs over.

### Changed
- **The format id moved to `grownet.interaction_network/v1`** (Karoline, 2026-10-04, on her agent's
  recommendation; Craig's question on #107), because `significance` changed meaning in this release and a
  version is the one signal that says so: a reader branching on the id would otherwise read these numbers
  as 0.1.x ones, silently. The namespace is unchanged, nothing else about the format moved, and the fields
  added since v0 are optional. A v0 document is still valid, read with the older meaning, and
  `grownet validate` names the version it read. The daily All network is used only when it speaks this
  version, so the page derives live until the workflow republishes it, about a day.
- **`significance` is now -log10 of the q-value, and the corrected p-value has its own field, `q_value`**
  (Karoline, 2026-10-03). Before, `significance` held the corrected p-value itself, so the name ran
  against the number: larger looked stronger and was weaker, and a continuous Cytoscape mapping on it was
  backwards. Now `p_value` is Welch's raw value, `q_value` is that value corrected for multiple testing,
  and `significance` is -log10 of the q-value: 0 at q = 1, larger is stronger evidence, capped at 15 for a
  q-value of zero. The page's column is `q`, the viewer shows p, q and significance, and the filter
  (`--max-adjusted-p`) still acts on the q-value. A reader of an older file gets the old meaning: the
  change rides with 0.1.1, which has no released files yet.
- **Arcs below the absence threshold are left out of every output by default** (Karoline, 2026-10-03), so
  the page, a downloaded file and a network sent to Cytoscape all hold the same arcs: Cytoscape used to
  count the absences too, which was confusing. They are still reported, in their own section of the result
  and in the report, with how many and at which k; `meta.hidden.absent` counts them and
  `meta.absence.absent` still says how many the threshold marked. The new setting **Include arcs below the
  absence threshold** (`--include-absent`) puts them back in the file, with `effect_over_sd` on each, for
  moving the threshold inside Cytoscape.
- **Continuous culture is derived with the growth measure `max`** (Karoline, 2026-10-03): the level a
  chemostat or serial dilution settles at is comparable with and without a partner, while the area under
  its curve and its growth rate are not. Such arcs carry the caution `continuous_culture` and are shown.
  With `auc` or a growth rate they are still left out unless `--include-non-batch` is given, and then they
  keep the `non_batch` quality flag and stay hidden by default. A comparison never mixes modes. No network
  changes today: no study in mGrowthDB has a non-batch pairwise or drop-out design.
- **A gLV mode button beside All** (`--glv-mode`), which toggles what a simulation needs: Report growth rates
  on and Include drop-out communities off, both left in sight in Advanced settings with their defaults
  unchanged (Karoline, 2026-10-04: "how about moving both options back to advanced parameters, with their
  default settings, and instead introduce a button 'gLV mode' next to 'All', which will enable growth rate
  collection and disable drop-out communities?"). A drop-out arc may act through a third species, while a
  gLV coefficient is meant to be the direct effect of one organism on another. The text beside the buttons
  is two sentences now, and the gLV package and the R object count the drop-out arcs they hold, or say that
  none is there. Pressing it again puts both back to their defaults, and it is drawn as a switch: the slider
  is green when the mode is on and white when the settings are the defaults (Karoline, 2026-10-04). It is
  still a submit button, so the page needs no JavaScript for it. The result section's control is **Get gLV parameters**, the two input boxes line up whether or
  not their examples wrap, and the help's R example plots the simulation with `matplot` and says that every
  arrival prints in R and that `grownet_listen()` takes one parameter set per call.
- The result table's third column is **sign**, not direction: an arc already has a direction, from the
  source to the species it affects (Karoline, 2026-10-03).
- A number the derivation never computed reads as **not computed** on the page, and a comparison with no
  ratio (obligate, abolished) reads as **no ratio**, rather than leaving the cell blank. In the file and in
  Cytoscape such a number stays missing: null in JSON, left out of GraphML and of what Cytoscape is sent,
  never 0 (Karoline, 2026-10-03).
- A number that is empty is left out of what is sent to Cytoscape rather than sent as null: Cytoscape turns
  a null number into 0.0, and a q-value of 0 is the strongest there is, so an untested arc used to pass a
  "q below 0.05" filter inside Cytoscape. The columns an arc may not carry (`p_value`, `q_value`,
  `significance`, `strength`, `weight`, `effect_over_sd`, `sd`, `se`, the replicate counts and the merge
  counts) are declared on the edge table instead, so every arc carries all of them and the cells of the
  arcs without a value stay empty. Without that, a network whose arcs are all untested had no such column
  at all. Checked against Cytoscape 3.10.3.
- Opening the page's address without its token, by hand or from a tab left over from an earlier run, shows
  grownet's own page saying where to find the link, instead of a bare server error (Karoline, 2026-10-04:
  "localhost:8791 shows an error"). It is still refused, with 403, and the page never shows the token.
- The first advanced setting is **Growth property**, not Growth measure (Karoline, 2026-10-03).
- The help says plainly that the adjusted p-value is the q-value, in the section on how an interaction is
  decided and in the setting that filters on it, and the page, the report and the legend call it the
  q-value throughout, since the result table heads that column q.
- The help page explains how a continuous culture is treated, in "Which growth measure": derived with max
  and marked `continuous_culture`, left out with an area under the curve or a growth rate and why, what
  the setting does then, that a comparison never mixes modes, and that no study in mGrowthDB holds such a
  design today.
- The tool's name is marked as a name in running text, on the page, in the help and in the README, since it
  is all lowercase and a sentence starting with it read like a typo (Karoline, 2026-10-03). Commands,
  paths, link labels and the page title keep it plain.
- The README carries the name the way the help does, grow**net** in running prose, its title is lowercase
  throughout (Karoline, 2026-10-04), and the sections that had grown by accretion were rewritten: what the
  local page offers is now two boxes, four buttons and the result, "What it does" names the medium and the
  shapes a network can leave in, and the derivation section says that a comparison never mixes media.
- Commands keep the name plain, in the help and in the README: the styling that marks grow**net** as a name
  in prose never touches something a reader would type (it had reached `library(grownet)` in one command
  line entry).
- **What ships with the tool describes the released state**, not the branch it was written on (Karoline,
  2026-10-04: "The help should refer to the stage the tool is in when released"): the R install line in the
  help, the page and both READMEs is the plain `install_github("crossfeed-bio/crossfeed", subdir = "r")`,
  and installing from a branch or a clone is a development step, in CONTRIBUTING.md. A test refuses an
  install line pointing at one of our branches, or wording about work in progress, in anything a reader
  sees, including every page the local server renders.
- Each release's notes on GitHub open with how to start the Windows program and get past the "Windows
  protected your PC" warning: the small More info link, and only then Run anyway (as Karoline found on
  Windows). The README and the zip's README.txt say the same, more precisely than before. Signing through
  the SignPath Foundation waits until the project can show the use and trust it asks for.
- The README's PyPI section no longer offers the pre-release install from the repository, and says to
  use one install route at a time and what to do when pipx finds a `grownet` command left by an earlier
  `pip install --user` (found by Karoline).

## [0.1.0] (2026-09-29)

The first release, on PyPI (`grownet`) and as a Windows program. It holds everything since 0.0.1; 0.0.2
was never published.

### Added
- All reads the network the repository derives once a day (#96): `.github/workflows/all-network.yml`
  derives All with the default settings and publishes it as the assets of the `all-network` release. The
  page's All button and `derive --all` use it when it is less than a day old and the settings are the
  defaults, and derive live otherwise, or with `--no-published`; the page and the report say when it was
  derived. One derivation a day instead of about 1,300 requests to mGrowthDB per All. A failed daily
  build opens an issue labeled `all-network-failed`, closed by the next build that succeeds.
- Every derived network carries the page's caution on how to read it in `meta.provisional` (a graph
  attribute in GraphML), so a download or the daily All network states its own terms without the page.
- The local page offers the Cytoscape style as a download (`/grownet_style.xml`, the file `grownet style`
  writes), linked from the help page's Cytoscape answers, so styling a GraphML file needs no command line.
  Help, Legend and About have a Back at the upper right as well as at the end, and the grownet mark leads
  back to the search being worked on instead of an empty page.
- The help page compares the three growth measures (area, maximum, growth rate): what each captures, and
  its strengths and weaknesses. The README calls the tool grownet, keeping crossfeed only for the command,
  the module, the repository and the schema id until the rename is released.
- A monoculture set is also matched to a co-culture by identical wording of how it was grown, once the
  organisms and the kind of culture are set aside (register item 28): SMGDB00000014's five co-cultures
  now give 10 arcs. An obligate or abolished arc whose set without growth is zero from its first time point
  carries the caution `zero_at_start`.
- With max as the growth measure, arcs are checked for stationary phase (register item 27): the caution
  `stationary_phase_differs` marks an arc where one set reached stationary phase within the compared window
  and the other did not, and `stationary_unchecked` one whose curves have under 6 time points. The rule is
  not fooled by a diauxic shift: a pause followed by a measured second rise is not stationary.
- An All button beside Example (`derive --live --all`): the box is ignored and every study in mGrowthDB is
  derived, with every partner; Only these studies and Exclude these studies still apply (register item 25).
- Merge to genus (`--merge-genera`), an advanced setting off by default: one node per genus, and the arcs
  between two genera merged by sign, with the median log2 mean and new arc fields `supporting_pairs` and
  `merged_pairs` (species pairs, or strain pairs when only taxon ids were entered). Interactions within a
  genus stay as a self-loop; absent arcs as one hidden absent arc per genus pair. With Merge parallel arcs
  on too, a pair measured in several studies counts once. Nodes gain the identity `genus` (item 24). The
  genus skips qualifiers (Candidatus, unclassified, uncultured) and keeps NCBI's brackets, so [Clostridium]
  is not Clostridium, in the merge, the genus query and the genus colors alike.
- A genus entered alone ("Blautia") stands for every species of it in mGrowthDB, listed on the page and
  in the report, instead of being refused as "a genus alone".
- The README says the tool is now called grownet and what keeps the crossfeed name until the rename, that
  the tests also run on Windows and macOS, and that the local page's About says who built the tool.
- An About button beside Help (#80): who built grownet, in the wording Craig agreed to on #80, with the
  repository link and the version.
- The help page opens with the idea behind the tool, after Gause (1932, 1934): grow two species alone
  and together and compare. A figure, drawn from code with the Baranyi-Roberts model the tool fits, shows
  each species alone, both together, and the arcs the change gives, and marks the three growth measures
  the tool can compare (area, maximum, growth rate). Tests keep the figure in step with the measures.
- The help page now explains every advanced setting (with its command line flag and default), every arc
  and node attribute, the main design decisions and why, the command line with the page's own example,
  what to do when no network comes back, a short Q&A, how to cite, and links the issue tracker. Tests
  require an entry for every setting, command line option and model field, so it cannot fall behind (#78).
- `derive --live --species NAME ...` runs the local page's search from the command line, with
  `--all-partners` for the page's "only the species entered" box unticked (#78).
- The report and every network record when the search ran (date, time and offset) and the version of
  the data: mGrowthDB publishes none for the whole database, so each study's upload and publication
  dates. Input that gives nothing now says why, per entry (unreadable, a taxon id mGrowthDB does not hold,
  a genus alone, an unknown name, with suggestions), commas and `txid` ids are understood, an empty result
  names the setting that caused it, and the Cytoscape messages say what to do on the page and the
  command line alike.
- `derive --report FILE` writes the page's report from the command line, and `crossfeed derive --help`
  groups its options as the page does (what to derive, the settings, the outputs), in the page's
  wording, with examples. A test requires an option for every setting and all three outputs.
- Clearer advanced settings: the absence threshold says it decides when an interaction counts as absent
  (the species do not affect each other), and the no-growth settings say they test the replicate growth
  curves of one species in one culture condition. A new setting, Exclude these studies
  (`--exclude-studies` with `--species`), leaves the listed studies out of a search; empty by default.
- Release automation (#26, #27): a version tag runs `.github/workflows/release.yml`, which checks the tag
  against the version and this changelog, tests the wheel in a clean environment on Linux, Windows and
  macOS, builds and starts the Windows program, publishes to PyPI through trusted publishing once a
  maintainer approves, and creates the GitHub release with the notes from this changelog and
  `grownet-<version>-windows.zip` attached. CI builds and starts both on every push. A double-clicked
  `grownet.exe` opens the page, and on an error waits for Enter instead of closing. RELEASING.md gives the
  setup and the steps; the README's install section offers the Windows zip, uv and PyPI.
- The gate gained a merge-marker check, after conflict markers from a merge reached this changelog
  unseen (now removed, both sides kept).
- Documentation made to agree with the code, after an audit (21 conflicts): the README's Cytoscape style,
  output example and field descriptions, technique rule, metric options and correction; the help page's
  effect, community and empty-result wording; "k = 0 marks only a mean of exactly zero absent" everywhere;
  METHOD_NOTES' defaults at a glance, rewritten from the running code; the viewer's derivation panel,
  which described the retired baseline, replaced by a plain statement. The viewer's GraphML now writes all
  of export.py's keys (it wrote 9 of 34), and a test runs it with Node against the CLI's. Page and CLI
  defaults are checked equal by a test.
- Merge parallel arcs (register item 14, Karoline's choices): an advanced setting, off by default
  (`--merge-arcs`), making the arcs of each source and target, across conditions, studies and evidence, one
  arc with the median log2 mean and its range; arcs whose signs disagree are not merged, absent arcs stay
  separate. Minimum supporting studies (`--min-studies`) keeps arcs resting on that many studies. Edges
  gain `merged_arcs` and `strength_range`.
- A species is compared only when its monocultures and co-cultures (or full community and drop-out) were
  measured by the same technique, not only in the same unit (Karoline, METHOD_NOTES item 23). No edge in
  mGrowthDB changed; it guards future data.
- With "only interactions between the species entered" (the default), a search reads only what can give
  such an interaction: monocultures and co-cultures of the entered strains, and whole drop-out designs
  holding two of them. Searches take about half as long (the Example about 2 s once the species list is
  in); checked on eight searches, the networks are identical to reading everything.
- The standalone viewer (`gui/index.html`) draws the legend's colors, one arrowhead, dashes for evidence
  and quality, and genus colors. CI also runs on Windows and macOS. The species list looks 25 missing
  study ids ahead instead of 5. Download, Report and Send to Cytoscape answer for the search on screen. A
  study of monocultures only says so.
- A strain is shown by its current name (#24, Karoline's rule of 2026-09-18): the name used by the most
  recently published study holding its taxon id, in the network's nodes and the resolved list; old names
  still find it. Taxon 411483 now reads Faecalibacterium duncaniae throughout.
- Growth rate as a metric (#41): `--metric growth_rate` and the Growth measure setting, with the
  implementation as its own setting (`--rate-method`): easylinear by default, as mGrowthDB computes its
  reported rates (it matched them on 190 of 192 curves within 10%), window 5 (`--rate-window`); or a
  guarded Baranyi fit, where a curve the model does not describe is left out and reported. The edge's
  metric names the rule (`growth_rate:easylinear:5`). The default for interactions stays auc.
- Faster: the Example search takes about 10 s from a cold start instead of 84 s, and about 4.5 s for a
  later search in the same session instead of 25 s. Nearly all the time was requests made one after
  another; they are now made six at a time over kept-open connections (`crossfeed.fetch`), and the
  derivation reads them from the cache it always used. Checked on every study: records, skip reasons
  and the species list are identical to the one-by-one version. A growth curve download is now retried
  like every other request.
- Conditions recorded only in descriptions (Karoline, METHOD_NOTES item 22): monocultures are pooled only
  when their descriptions agree; a co-culture uses the monoculture set whose description names it, or is
  skipped with the reason when several fit; edges from description-only variants carry the new caution
  `conditions_unverified`; failing a name, the set whose name has the same qualifier ("Evolved AtCt" with
  "Evolved At"). SMGDB00000014 now derives nothing, each pair saying why.
- Nodes in Cytoscape: each genus its own color (Karoline), from a list of 48 ordered by how distinct each
  stays. Fixed: a second send in one Cytoscape session arrived unstyled, because updating the existing
  style asked CyREST to delete all mappings at once, which it refuses; they are now deleted one by one.
- Fixed: Send to Cytoscape delivered the network without its style. CyREST applies styles and layouts
  by GET and refused the POST (405), and the error was swallowed. The style is now called grownet,
  brought up to date in place when Cytoscape already has it, and a failure is reported on the page.
  Nodes are colored by genus (the first word of the name): four hues checked for color vision
  deficiency against the arc colors, and further genera each their own color from a list ordered by
  how distinct it stays; labels sit under the nodes.
- The species box starts empty, under the header "Species, strains or NCBI taxon ids" and a smaller row
  of examples (a species, a strain, a taxon id). An empty result says which step found nothing. GraphML
  nodes carry a `label` (the strain name), which Gephi uses as the node label.
- The result appears on the same page, under the settings that produced it (#74); a search in progress
  shows a progress bar and the page updates by itself, without JavaScript (#75); three outputs sit above
  the table: Download network with a JSON or GraphML menu, Send to Cytoscape, and Report, the detailed
  comments of the search with every setting and the tool version, shown on the page and downloadable as
  a text file (#76). `tests/test_interface.py` checks each of Karoline's requirements for these.
- The local page is drawn in the grownet style Karoline approved: a header with the mark, the name and
  the version, Legend and Help; one green primary action; quiet table headers, directions in the legend's
  two colors (inhibition the orange-red #C2410C) and flags as pills. The legend opens inside the same
  frame. The page, the help and every network's `meta` name the tool grownet; the command stays
  `crossfeed` until the package is renamed (#71).
- The tool version shows next to the name on the local page. Every network's `meta` records the tool,
  `tool_version`, `derived_on` and every setting used; GraphML carries the first three as graph
  attributes (#78).
- The local page gained an Example button, which fills the species box with a pair that derives a network
  (Faecalibacterium duncaniae and Blautia hydrogenotrophica), and a Help button opening a help page that
  explains what the tool does, how to read a result, and links the legend (#73).
- The mark (`docs/logo.svg`): three nodes joined by directed edges, green for facilitation and red for
  inhibition, both with the same arrowhead. It is the page's favicon and sits beside its title.
- A legend (`docs/legend.svg`, `make legend`, and "What the arcs mean" on the local page): one picture of
  what each arc, head, dash and flag means. It is drawn from the code, and a test requires it to name every
  value in the model's vocabulary, so it cannot drift from what the network shows.
- Chemostat and serial dilution experiments are left out of a derivation by default (#42), reported with
  their mode, and derived with `--include-non-batch` or the matching advanced setting, where their edges
  are flagged `non_batch`. An experiment with no recorded mode counts as not batch. Edges gained
  `cultivation_mode`. SMGDB00000001, SMGDB00000005 and SMGDB00000011 now say why they derive nothing.
- Send a network into a running Cytoscape (#25): `crossfeed derive ... --to-cytoscape` and a
  "Send to Cytoscape" button on the local page post it through CyREST on localhost, with the style the
  legend describes (direction by color and arrowhead, width by weight, absent edges hidden, drop-out arcs
  long-dashed and single-replicate arcs dotted). `crossfeed style` writes the style as a file instead.
  Cytoscape not running is reported with the port, never as a traceback. No new dependency.
- The no-growth rule (#37): before any ratio, a species counts as grown in a replicate set only when its
  rise from the first time point, log2(maximum / start) per replicate with each maximum at its own time,
  is significant (paired t-test, alpha 0.05) or reaches 1.5 times as a geometric mean. A set that did not
  grow feeds the existing `obligate`, `abolished` and `no_growth` outcomes instead of a ratio between two
  near-zero quantities. Both numbers are settings (`--no-growth-alpha`, `--no-growth-factor`, and the
  advanced settings on the local page), and `meta.no_growth` records them with the obligate and abolished
  counts. In SMGDB00000013 this makes Comamonas to Ochrobactrum obligate.
- A pluggable derivation seam (`crossfeed.derive.Deriver`): the comparison method is a drop-in strategy,
  with the provisional `BaselineDeriver` as one implementation. The agreed method arrives as another
  `Deriver` without touching the model or the pipeline.
- A generic command line (`python -m crossfeed derive|validate|schema`, and a `crossfeed` console script)
  that derives a network for any mGrowthDB study, validates a network document, or emits the schema.
- A `--deriver MODULE:CLASS` flag on `crossfeed derive` to run a custom derivation method live with no
  glue code, plus a complete, runnable `examples/custom_deriver.py` and tests that keep it working.
- The README rewritten as a complete guide: install, run, the output format with an annotated example,
  and how to plug in a method end to end, so a new contributor never has to root around other docs.
- A published JSON Schema for the neutral format (`schema/interaction_network.schema.json`) plus a
  dependency-free `crossfeed.schema.validate_document`.
- `crossfeed gui`: a local page (standard library server on 127.0.0.1, a token in the URL, no JavaScript)
  where you type species names or NCBI taxon ids and get their interactions as a table, with every
  setting behind "Advanced settings" and downloads for JSON and GraphML.
- The pipeline now derives through the comparison the collaboration specified: `ReplicateDeriver` is the
  default for a live derivation, comparing replicate sets on the log2 scale (area under the curve by
  default, maximal abundance selectable with `--metric`), so every edge carries a standard error, the
  replicate counts, and the outcome. `BaselineDeriver` remains only as the retired placeholder.
- Network edges gained optional `p_value`, `weight`, `effect_over_sd`, `status`, `sd`, `se`, `n_with`, `n_without`, `outcome`, `metric`, `quality`, and
  `notes` fields, in the model, the JSON Schema, and GraphML.
- Presence and absence follow an absence threshold k: an edge's `status` is `absent` when its
  |log2 mean| is below k times its standard deviation, `present` otherwise (default k = 1, the mean plus
  or minus sd rule; `--absence-threshold`, 0 marks nothing absent). Every tested comparison is exported as
  an edge with `status`, `weight` (|log2 mean|, always positive) and `effect_over_sd` (|log2 mean| / sd), so
  the threshold can be changed later, including in Cytoscape; the display hides absent edges by default.
  There is no neutral edge. Low-quality edges (a single replicate, pooled strains) keep the sign of their
  mean, are flagged in `quality`, and are left out by default (`--include-low-quality`).
- Welch's t-test on the per-replicate log2 values is reported on every comparison with two replicates per
  side, with the raw `p_value` and the Benjamini-Hochberg adjusted `significance`; it supports an edge but
  does not decide one (`crossfeed.stats`, standard library only).
- An implausible spike in a growth curve is flagged and that curve left out for its species only, never
  dropped silently (`crossfeed.growth.spike`: one or two consecutive interior points more than the limit above both
  neighbours, default limit 100, 0 to switch off). The report names the time points and, for the flagged strain, whether other measurements
  of it in the same replicate are clean; a community trace counts only in a monoculture.
- `crossfeed.adapter`: mGrowthDB experiments become replicate growth curves, so the comparison the
  collaboration specified (`crossfeed.interaction`) can run on real data. Time series come from the CSV
  representation of a measurement context (`MGrowthDBClient.get_measurement_series`); `Average(...)`
  bioreplicates are left out, since they are the mean of the real replicates.
- `crossfeed.taxonomy`: species names resolved to NCBI taxon ids from mGrowthDB's own strain records
  (`species_index`, `resolve_species`), so a person can type names where the API takes ids. A name
  resolves to every taxon id mGrowthDB holds under that genus and species, species level and strain level.
- A GraphML export (`crossfeed derive --format graphml`, and `crossfeed.export.to_graphml`) so a network
  drops straight into Cytoscape, igraph, networkx, or Gephi. Dependency-free (standard library xml only).
- Optional `evidence` (`biculture` or `dropout`) and `community` fields on network edges, in the model,
  the JSON Schema, and GraphML, so arcs from drop-out communities (not necessarily direct) are labeled
  apart from mono versus bi-culture arcs. The provisional baseline marks its edges `biculture`.
- mGrowthDB client hardening: in-memory and optional on-disk response caching, and retries with backoff
  on transient network failures and 5xx responses.
- An expanded guardrail gate (`checks/gate.py`) covering secrets, raw data, local-machine paths,
  self-contained imports, house style (ASCII punctuation, US spelling, no hedging caveats), and a schema
  contract check. A pre-commit hook and a Makefile run the gate, tests, and lint the same way CI does.
- Helpers for a pairwise interaction strength from replicate growth curves: `crossfeed.growth`
  (`GrowthCurve`, `Replicate`, unit and species checks across replicate sets, `curve_features` for the
  area under the curve and maximal abundance over a shared time window) and
  `crossfeed.interaction.interaction_strength` (per species, the difference of mean log2 growth property
  between co-culture and monoculture replicates, with standard deviation, standard error, and n).
- A shared workflow for coding agents: `AGENTS.md` (instructions and the mayor, worker, and verifier
  roles), Feature and Task issue forms, and `docs/agents/NOTES.md` as shared agent memory.
- `crossfeed.interaction.dropout_interaction_strengths`: arcs from drop-out communities (the full
  community against the community without one species), using the same log2 set comparison as
  `interaction_strength`, with each arc labeled `dropout` (not necessarily direct) or `biculture` and its
  community recorded.
- Zero growth is reported as a result instead of an error: a target that grows only with the source present
  gets the outcome `obligate` (obligate commensal or mutualist), one that grows only without it `abolished`,
  in both `interaction_strength` and `dropout_interaction_strengths`.

- Drop-out designs reach the default network (#47): a community plus experiments holding it without one
  member give arcs labeled `evidence: dropout`, included by default and left out with `--no-dropout` or
  the matching advanced setting. Experiments are pooled only under identical conditions, and
  SMGDB00000008 now derives.
- Edges gained optional `cautions` (`two_replicates`, shown without making an edge low quality) and
  `experiments` (the ids of the experiments an edge compares), plus the quality flag
  `removed_member_detected`.

### Fixed
- A file the command line cannot read or write (a missing fixture, an output folder that does not exist,
  a file that is not JSON) is reported in one line, with the folder a relative path was read from, instead
  of a traceback. The README's offline Quickstart says it runs from a clone: the fixture is in the
  repository's `tests/fixtures`, not in an installed grownet (found by Karoline after a pip install).
- The style file imports in Cytoscape: `grownet style` and the help page's download now write Cytoscape's
  XML style format (`grownet_style.xml`). File, Import, Styles from File refused the JSON file with "Don't
  know how to read file" (found by Karoline in Cytoscape 3.10.4); Cytoscape reads no JSON style file, its
  own exports included. Send to Cytoscape was not affected.

### Changed
- Fewer requests to mGrowthDB, with identical networks (checked on all of mGrowthDB): a monoculture no
  co-culture of its study is compared with is no longer read (All: 3709 -> 1313 requests, 26 s -> 9 s), and
  the local page keeps what it has read for an hour, renewed with the species list, so a second search
  reads only what is new (the Example after All: 141 -> 4 requests). The skip list no longer lists the
  replicates of monocultures that were never compared (All: 1961 -> 191 entries).
- The rename (#71): the package, the module and the command are `grownet` (`grownet derive ...`, `python -m
  grownet`, `uvx --from git+https://github.com/crossfeed-bio/crossfeed grownet gui`), with no `crossfeed`
  alias, since nothing had been released. The repository address and the method label stored in each
  network (`crossfeed replicate v1`) are unchanged. The README is titled "grownet: Growth-curve
  derived interaction networks".
- The schema id is `grownet.interaction_network/v0` (#71, Craig's half of the rename). A new namespace at
  the same version: the format itself does not change, and a version states what the content is, not what
  it is called. The id is written into every network grownet saves, so it is changed before 0.1.0, while
  nothing has been released and no published file carries the old one. A document with the old id is
  rejected with a message naming both, rather than accepted silently, so one format keeps one id.
- The Baranyi growth-rate fit uses the curve up to the end of the plateau after its maximum, not the whole
  curve, so a decline after the peak no longer rejects it (register item 29): 30 -> 40 arcs on mGrowthDB.
- A curve that starts after its design's common start leaves its replicate out of that member's own arcs
  only; the replicate still serves the other members (SMGDB00000008: 24 arcs regain a second replicate).
  The page, the report and the command line list average replicates as one line per experiment.
- Each bi-culture arc is compared over its own window, the target's curves alone and together, as drop-out
  arcs already were, so the partner's shorter monoculture no longer shortens it (register item 26). On
  mGrowthDB one arc changes (SMGDB00000006, L. bulgaricus -> S. thermophilus STpos: +0.088 to +0.074,
  absent either way).
- Inhibition is drawn in orange-red (#C2410C) rather than red (Karoline, 2026-09-27). With uniform arc
  tips the color is the only cue for the sign, and green against red is the hardest pair for a reader with
  a color vision deficiency: simulated, the new pair stays about 90 sRGB units apart under protanopia and
  deuteranopia, where green and red managed 58. `tests/test_palette.py` keeps it that way.
- Arcs end in the same arrowhead whether they facilitate or inhibit: the color carries the sign, in the
  legend and in the Cytoscape style (Karoline, 2026-09-27). The bar head is retired.
- Nodes are strains keyed by NCBI taxon id (`ncbi:411483`) and named with the strain name, with `taxon_id`,
  `species` (genus and species from the name) and `identity` as node fields (#23). Monocultures are matched
  to co-cultures by taxon id, so another strain of the same species is never used: in SMGDB00000006,
  L. bulgaricus to S. thermophilus LMG 18311 is now obligate instead of a +2.93 edge computed against the
  STpos strain's monoculture. A taxon id a study gives to different strains falls back to names.
- Single-replicate edges are shown by default, keeping the `single_replicate` flag and an undetermined
  status, for the Cytoscape style to mark; the other low-quality flags stay hidden by default.
- A co-culture is compared only with monocultures grown under the same conditions (cultivation mode and
  compartments); no current study is affected.
- crossfeed now has no runtime dependencies: the client uses the standard library `urllib`, and the
  unused `requests` dependency was dropped.

### Fixed
- From Karoline's checks (audit step 8): Help, Legend or About opened from a result, then Back, returned to
  an empty page and the result was lost; their links and Back now carry the search, so Back returns to it.
  A GraphML file imported into Cytoscape did not take the whole grownet style, because the file lacked the
  columns the style maps; GraphML now carries genus, genus_color, line_style and display_weight, from the
  tool and the viewer alike, and the viewer's genus rule matches the tool's (qualifiers skipped, NCBI's
  brackets kept). The help page says how to style a GraphML file in Cytoscape, and that Gephi may merge
  parallel arcs on import.
- From a code review of the whole package (2026-09-28): with the growth rate (easylinear), a curve that only
  declines crashed the comparison and dropped the whole pair or community (SMGDB00000014 lost three
  co-cultures); its rate is now its steepest, non-positive slope. A problem with one species (mixed
  abundance units, a technique mismatch, a later start) now leaves out that species' arcs only, not the
  pair or the community, and units are checked per species, since each is compared only with itself. The
  no-growth rule, the stationary check and the zero-at-start check leave out replicates excluded for a
  spike. Merge to genus counts a strain that studies name differently once. The local page keeps its 20
  latest searches, reads the species list again after an hour, and builds it once when two searches start
  together.
- When mGrowthDB could not be reached (a network failure, a timeout, server errors), the species list came
  back empty and a search said the species were not in mGrowthDB. Only "no such study" (HTTP 404) now ends
  the crawl; anything else stops the search with "mGrowthDB could not be read". A replicate or growth curve
  that fails to download partway through a search now marks the result incomplete at the top of the page,
  in the report and on the command line, instead of only among the pairs the data did not support.
- A node keyed by name, because mGrowthDB gives its taxon id to more than one species, keeps its own name:
  the current-name step renamed it by the id's latest name, so in SMGDB00000008 Lachnoclostridium
  symbiosum WAL-14673 appeared as a second L. clostridioforme (found by the audit of 2026-09-28).
- The README and the help page now say that curves are compared over the time window they share.
- "Only interactions between the species entered" no longer drops every edge when a study records a strain
  under another name: a species entered as Faecalibacterium duncaniae now matches the same taxon recorded
  as Faecalibacterium prausnitzii, because the filter matches taxon ids as well as names (#73).
- The spike guard no longer mistakes a die-off or late growth for a spike (#62). It compared a curve's
  maximum with its median, which flagged curves spanning several orders of magnitude (22 curves in
  SMGDB00000013, 7 in SMGDB00000014, 2 in SMGDB00000004) and emptied whole replicate sets. A spike is now
  one or two consecutive points above both neighbours by the limit, never the first or last point. The
  BH_14 spike it was built for is still caught; SMGDB00000013 goes from 10 edges to 16.
- An obligate or abolished edge is no longer flagged `single_replicate` for having no growing replicates on
  the side where no growth is its result; that side counts its replicates without growth (#47).
- A comparison whose replicate set was emptied by exclusions (every replicate spiked) is skipped with a
  reason instead of being reported as obligate or abolished; four such edges in SMGDB00000013 were false.
- The viewer in `gui/` shows an edge's `evidence`. A `dropout` arc is labeled indirect in the interaction
  list, the detail panel, and the hover text, carries the community it came from, and is drawn with an
  open ring at its midpoint. The ring is a channel the sign does not use (sign stays color, dash, and
  arrowhead), so an arc that may act through a third species no longer reads as a direct one.
- The baseline reports a monoculture it had to drop. Nodes are keyed at genus and species, so two strains
  of one species share a key and only the last monoculture read is used; that collision now appears in
  `skipped` naming both strains instead of passing silently. Which strain to keep is a method choice
  (see "Open decisions" in `docs/METHOD_NOTES.md`), so the derivation itself is unchanged.

## [0.0.1] (2026-09-14)

### Added
- Initial public release: the neutral interaction-network model with edge-level attribution, the live
  mGrowthDB API client, and the FP/BH first slice running on the published study SMGDB00000004 and
  recovering Blautia hydrogenotrophica facilitating Faecalibacterium prausnitzii.
