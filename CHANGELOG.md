# Changelog

All notable changes to grownet (called crossfeed before 0.1.0) are recorded here. The format follows Keep
a Changelog. A released version is a promise about content: a tagged version is never reused for changed
content.

## [0.1.1] (unreleased)

### Changed
- **Include drop-out communities moved out of Advanced settings**, beside the All button and Report growth
  rates, so it is visible that it is on (Karoline, 2026-10-04: "for gLV, including drop-out communities are
  not a good idea, but they are enabled by default. I'd like to keep them by default. I suggest moving this
  out of advanced options and next to 'Report growth rates', so people see it's enabled"). The default is
  unchanged, and the text beside it says to untick it for gLV parameters, where a coefficient is meant to be
  the direct effect of one organism on another. The gLV package and the R object now count the drop-out arcs
  they hold, or say that none is there.
- Opening the page's address without its token, by hand or from a tab left over from an earlier run, shows
  grownet's own page saying where to find the link, instead of a bare server error (Karoline, 2026-10-04:
  "localhost:8791 shows an error"). It is still refused, with 403, and the page never shows the token.
- **Arcs below the absence threshold are left out of every output by default** (Karoline, 2026-10-03), so
  the page, a downloaded file and a network sent to Cytoscape all hold the same arcs: Cytoscape used to
  count the absences too, which was confusing. They are still reported, in their own section of the result
  and in the report, with how many and at which k; `meta.hidden.absent` counts them and
  `meta.absence.absent` still says how many the threshold marked. The new setting **Include arcs below the
  absence threshold** (`--include-absent`) puts them back in the file, with `effect_over_sd` on each, for
  moving the threshold inside Cytoscape.
- The first advanced setting is **Growth property**, not Growth measure (Karoline, 2026-10-03).
- The help says plainly that the adjusted p-value is the q-value, in the section on how an interaction is
  decided and in the setting that filters on it, and the page, the report and the legend call it the
  q-value throughout, since the result table heads that column q.
- The tool's name is marked as a name in running text, on the page, in the help and in the README, since it
  is all lowercase and a sentence starting with it read like a typo (Karoline, 2026-10-03). Commands,
  paths, link labels and the page title keep it plain.
- The help page explains how a continuous culture is treated, in "Which growth measure": derived with max
  and marked `continuous_culture`, left out with an area under the curve or a growth rate and why, what
  the setting does then, that a comparison never mixes modes, and that no study in mGrowthDB holds such a
  design today.
- **Continuous culture is derived with the growth measure `max`** (Karoline, 2026-10-03): the level a
  chemostat or serial dilution settles at is comparable with and without a partner, while the area under
  its curve and its growth rate are not. Such arcs carry the caution `continuous_culture` and are shown.
  With `auc` or a growth rate they are still left out unless `--include-non-batch` is given, and then they
  keep the `non_batch` quality flag and stay hidden by default. A comparison never mixes modes. No network
  changes today: no study in mGrowthDB has a non-batch pairwise or drop-out design.
- The result table's third column is **sign**, not direction: an arc already has a direction, from the
  source to the species it affects (Karoline, 2026-10-03).
- A number the derivation never computed reads as **not computed** on the page, and a comparison with no
  ratio (obligate, abolished) reads as **no ratio**, rather than leaving the cell blank. In the file and in
  Cytoscape such a number stays missing: null in JSON, left out of GraphML and of what Cytoscape is sent,
  never 0 (Karoline, 2026-10-03).
- **`significance` is now -log10 of the q-value, and the corrected p-value has its own field, `q_value`**
  (Karoline, 2026-10-03). Before, `significance` held the corrected p-value itself, so the name ran
  against the number: larger looked stronger and was weaker, and a continuous Cytoscape mapping on it was
  backwards. Now `p_value` is Welch's raw value, `q_value` is that value corrected for multiple testing,
  and `significance` is -log10 of the q-value: 0 at q = 1, larger is stronger evidence, capped at 15 for a
  q-value of zero. The page's column is `q`, the viewer shows p, q and significance, and the filter
  (`--max-adjusted-p`) still acts on the q-value. A reader of an older file gets the old meaning: the
  change rides with 0.1.1, which has no released files yet.
- A number that is empty is left out of what is sent to Cytoscape rather than sent as null: Cytoscape turns
  a null number into 0.0, and a q-value of 0 is the strongest there is, so an untested arc used to pass a
  "q below 0.05" filter inside Cytoscape. The columns an arc may not carry (`p_value`, `q_value`,
  `significance`, `strength`, `weight`, `effect_over_sd`, `sd`, `se`, the replicate counts and the merge
  counts) are declared on the edge table instead, so every arc carries all of them and the cells of the
  arcs without a value stay empty. Without that, a network whose arcs are all untested had no such column
  at all. Checked against Cytoscape 3.10.3.

### Added
- **A second input box: media, experiments or studies** (Karoline, 2026-10-04, weakening her stance against
  environment filtering now that gLV parameters are exported: "it's one thing to export a network of known
  interactions and another to do a gLV simulation"). Optional, beside the species box, with its own
  examples. A medium is matched as text, case-insensitively, against the medium name mGrowthDB records on
  the experiment's compartments, its description and its name, so one word finds the four spellings of
  Wilkins-Chalgren in the database; an id picks one study (SMGDB...) or one experiment (EMGDB...), and
  naming a comparison keeps the monocultures it is made against, which the report lists. On the command
  line it is `--conditions NAME ...`. **"Only these studies" has left Advanced settings**: a study id typed
  in the box does its job, and the study argument of a `--species` search still works.
- The gLV package and the R object **name the media their numbers come from**, and say in capitals when
  there is more than one, since a simulation is of one environment: the All network's package reports six.
- **Every arc records its `medium`**, the growth medium the comparison ran in, in the neutral format, in
  GraphML, in what Cytoscape receives and in the report. The schema gained the optional field. Nothing
  about the method changed: a comparison never mixed media, because the medium is part of the conditions
  two replicate sets must share.
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
- `glv_scale()` in the R package, and a line in the gLV README and the help: the cells are often stronger
  than the -1 on the diagonal, and a simulation run on them unchanged can grow without bound and come back
  as NA. Measured on SMGDB00000004, where the unscaled matrix diverges and the scaled one settles.
- **The adjacency matrix as an export format** (`--format matrix`, the page's format menu): the network as
  a square CSV table, a cell holding the log2 mean of the comparison, so `A[i][j]` is the effect of j on i
  (rows affected, columns the actor). Each organism appears once, so arcs of one pair are merged across
  conditions and studies by their median; a pair whose arcs disagree in sign is left at 0; an empty cell
  and an arc below the absence threshold are 0. An obligate interaction carries +10 and an abolished one
  -10 (Karoline, 2026-10-03: "obligate and abolished arcs need to carry numbers reflecting the strong
  effect, how about 10 with the appropriate sign?"): neither has a log2 ratio, because one side did not
  grow at all, so the number is a stated extreme, named cell by cell in the gLV README, and it never enters
  the median of the arcs that do have a ratio. The diagonal is 0 here, and -1 in the gLV package.
- **Report growth rates**, a checkbox beside the All button (`--report-rates`), off by default: every
  organism in the network also gets its maximum specific growth rate in monoculture, by the chosen rate
  method, the median over the replicates and studies that have one, with each study's own median beside it
  in `meta.growth_rates`. Batch monocultures only (in a chemostat the rate is the dilution rate, and a rate
  from a co-culture is growth with a partner). The rates download as their own CSV (`--rates FILE`), and an
  organism whose curves give no rate is named on the page and in the report, never given a substitute.
- **Generate gLV parameters** in the result section, with the rates (`--glv FILE`): a zip holding
  `interaction_matrix.csv` (the matrix with -1 on the diagonal, by convention, for self-limitation),
  `growth_rates.csv` in the same order, and a `README.txt` that states the conventions, names any pair left
  at 0 for disagreeing in sign, and names every organism without a rate. The README says plainly that a
  cell is an effect size, not a fitted gLV coefficient, which is a per-capita effect in absolute units
  (Karoline, 2026-10-03).
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
