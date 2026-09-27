# Changelog

All notable changes to crossfeed are recorded here. The format follows Keep a Changelog, and versions
stay in the 0.0.x range while the interface settles. A released version is a promise about content: a
tagged version is never reused for changed content.

## [0.0.2] (unreleased)

### Added
<<<<<<< HEAD
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
- Fixed: Send to Cytoscape delivered the network without its style. CyREST applies styles and layouts
  by GET and refused the POST (405), and the error was swallowed. The style is now called grownet,
  brought up to date in place when Cytoscape already has it, and a failure is reported on the page.
  Nodes are colored by genus (the first word of the name): four hues checked for color vision
  deficiency against the arc colors, then gray; labels sit under the nodes.
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
=======
- The mark (`docs/logo.svg`): three nodes joined by directed edges, green for facilitation and red for
  inhibition, both with the same arrowhead. It is the page's favicon and sits beside its title.
>>>>>>> origin/cytoscape
- A legend (`docs/legend.svg`, `make legend`, and "What the arcs mean" on the local page): one picture of
  what each arc, head, dash and flag means. It is drawn from the code, and a test requires it to name every
  value in the model's vocabulary, so it cannot drift from what the network shows.
- Chemostat and serial dilution experiments are left out of a derivation by default (#42), reported with
  their mode, and derived with `--include-non-batch` or the matching advanced setting, where their edges
  are flagged `non_batch`. An experiment with no recorded mode counts as not batch. Edges gained
  `cultivation_mode`. SMGDB00000001, SMGDB00000005 and SMGDB00000011 now say why they derive nothing.
<<<<<<< HEAD
- Send a network into a running Cytoscape (#25): `crossfeed derive ... --to-cytoscape` and a
  "Send to Cytoscape" button on the local page post it through CyREST on localhost, with the style the
  legend describes (direction by color and arrowhead, width by weight, absent edges hidden, drop-out arcs
  long-dashed and single-replicate arcs dotted). `crossfeed style` writes the style as a file instead.
  Cytoscape not running is reported with the port, never as a traceback. No new dependency.
=======
- The no-growth rule (#37): before any ratio, a species counts as grown in a replicate set only when its
  rise from the first time point, log2(maximum / start) per replicate with each maximum at its own time,
  is significant (paired t-test, alpha 0.05) or reaches 1.5 times as a geometric mean. A set that did not
  grow feeds the existing `obligate`, `abolished` and `no_growth` outcomes instead of a ratio between two
  near-zero quantities. Both numbers are settings (`--no-growth-alpha`, `--no-growth-factor`, and the
  advanced settings on the local page), and `meta.no_growth` records them with the obligate and abolished
  counts. In SMGDB00000013 this makes Comamonas to Ochrobactrum obligate.
>>>>>>> origin/no-growth-rule
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

### Changed
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
