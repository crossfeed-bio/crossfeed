# Derivation method: settings and agreed defaults

mGrowthDB serves growth curves, not interactions. Turning growth into a directed, condition-specific
interaction is a scientific choice, and it belongs to the collaboration (K. Faust, H. Zafeiropoulos), not
to this code.

Following Karoline's suggestion, the choices below are user-configurable settings, not one fixed method.
Each has a sensible default. A user changes any of them by selecting a `Deriver` and its options on the
command line (see [CONTRIBUTING.md](../CONTRIBUTING.md)); the viewer in `gui/` shows the same settings so
a reader can see how a network was made. This note records the defaults. The "Proposed default" line
under each setting is Craig's opening vote, so there is something concrete to react to. Karoline and Haris
weigh in, we settle each default together, and the settled value ships as the default.

## What the default derivation does today

**Status 2026-09-21.** `ReplicateDeriver` is the default for a live derivation (#40). It reads each
replicate's measured curve through `crossfeed.adapter` (#38) and compares replicate sets with
`crossfeed.interaction.interaction_strength`, the comparison Karoline specified, so the defaults settled
below are shipped behavior rather than intentions. Every edge carries its mean, `sd`, `se`, replicate
counts, outcome, metric, `quality` flags and `notes`.

- **Area under the curve by default**, `max` selectable with `--metric` (setting 1).
- **Presence follows the spread**, not a fixed band: facilitation when the interval mean plus or minus
  sd lies above zero, inhibition when it lies below. When it crosses zero on data with no quality issues
  there is no interaction, which is the absence of an edge rather than a "neutral edge" (Karoline,
  2026-09-21): such comparisons are listed in `meta.absent` and never as edges (item 19).
- **Low-quality edges are computed and hidden**, with `--include-low-quality` to show them and
  `meta.hidden` counting what was left out (item 21).
- **A statistical test is reported, never used to decide** (Karoline, 2026-09-21): Welch's t-test on the
  per-replicate log2 values, `p_value` raw and `significance` Benjamini-Hochberg adjusted over every
  comparison tested in one derivation, named in `meta.statistics` (item 10).
- **An implausible spike in a curve is flagged and the curve left out for its species only** (#48),
  recorded on the edge as a note rather than as a quality issue while two replicates remain.

### The retired placeholder

`BaselineDeriver` remains only as the placeholder it always was, reachable with `--deriver` and no longer
the default. What follows describes it, and is kept because networks derived before 2026-09-21 came from
it. `src/crossfeed/derive.py` (`BaselineDeriver`) is a
transparent placeholder that runs the seam end to end on real data. For each pairwise (two-member)
co-culture it reads mGrowthDB's reported per-strain `growthRate`, and sets

    strength = log2(growthRate in co-culture / growthRate in monoculture)

for each of the two partners, one directed edge each. It does not fit the rate itself; it takes the value
mGrowthDB reports. Some consequences worth stating plainly, because several are open decisions below:

- **Point estimates, no uncertainty.** The shipped edge is a single number. It carries no standard error,
  no replicate count, and `significance` is null (every edge is qualitative). A separate replicate-aware
  path exists (`interaction.py`, standard error from replicate log values) but is not yet wired into the
  network the pipeline emits.
- **Nodes are keyed at genus and species, not strain.** The node id is the lowercased genus and species
  (`_gs` in `derive.py`), so two strains of one species collapse to one node. Nodes carry no NCBI taxon id
  yet, so a crossfeed network does not line up with a microbetag network on a shared key (see setting 7).
- **A fixed neutral band.** `|log2 ratio| < 0.25` reads neutral. The cutoff is a constant, not scaled to
  the noise of the pair (the baseline has no noise estimate to scale by).
- **Larger communities are skipped.** A co-culture with more than two members is recorded in `skipped`
  with a reason, not forced into a pairwise number.
- **One edge per condition, never merged.** Each condition and study makes its own edge; edges for the
  same interaction are not combined, so an edge's `study_ids` has one entry today (see setting 10).
- **Technique is recorded and a mismatch is flagged.** In the flagship study the monoculture is measured
  by flow cytometry or OD and the per-strain co-culture by qPCR; each edge records both and flags the
  mismatch (see setting 6).

## Defaults at a glance

1. Growth metric: **AUC** (settled 2026-09-19), `max` selectable, growth rate to follow once it has a rule
2. Per-strain signal in a community: **per-strain qPCR, as the study reports it**
3. Mono versus co comparison: **mean log2 over replicate sets** (settled), coupled to 1; the neutral call
   comes from the spread, not a constant band (item 19)
4. Significance and uncertainty: **sd, se and replicate counts on every edge** (shipped); presence
   follows the spread (item 19); Welch's t-test with Benjamini-Hochberg correction is reported as support
   and does not decide (settled 2026-09-21, item 10)
5. Co-culture scope: **pairwise, two member**
6. Technique mismatch: **flag on every edge**, and do not trust the sign near the band under a mismatch
7. Taxonomic identity: **genus and species today**, plus an NCBI taxid on every node (needs building);
   an edge whose monoculture set pooled two strains is flagged `strains_pooled`
8. Environment and medium: **keep all conditions, tag each edge**; restriction waits on mGrowthDB metadata
9. Drop-out (leave one out) communities: **include, labeled by evidence** (settled by Craig 2026-09-20);
   not implemented yet
10. Edge thresholds: **minimum strength 0, minimum supporting studies 1**, meaningful once edges merge
11. Minimum time points: **carry the fit quality mGrowthDB reports**, gate on it rather than a fixed count
12. Chemostats and serial dilutions: **flag and keep separate from batch**
13. Output format: **JSON canonical, GraphML on demand**
14. Query scope: **no default chosen yet**; whether a query for a species also returns its other strains,
    or other species of its genus (Karoline's list, 2026-09-18)
15. Absences of interaction: **listed in `meta.absent`, never edges** (settled 2026-09-21; replaces
    "show neutral edges", since a neutral edge is a contradiction)
16. Show low-quality edges: **off** (settled 2026-09-21); computed, flagged, and hidden

## 1 and 3. The growth metric and how mono is compared to co (one coupled choice)

These two are one decision, because the comparison has to suit the metric.

- **growthRate (1/h)** [baseline]: a rate, so it travels better across techniques.
- **AUC, maximum OD, or yield**: extensive quantities.
- **log2(co / mono) with a deadband** [baseline]: the comparison the baseline uses.
- **a difference, or a normalized effect size**: an alternative comparison.

A log ratio suits an extensive quantity (AUC, yield, biomass), where doubling is meaningful and the value
stays away from zero. On a growth rate the ratio is unstable: when the monoculture rate is small, the
denominator pushes the ratio to a large magnitude or flips its sign, exactly where an interaction looks
strongest. So the pairing the baseline ships, rate with a log ratio, is the first thing to reconsider.

**Proposed default (Craig): switch the pair to AUC with log2(co / mono), or keep growthRate and compare by
a difference.** I lean to AUC with the log ratio, since the log ratio is already implemented and AUC is
what it suits; growthRate's technique robustness is the reason to consider the difference instead. This is
a real choice for us to make, not a settled default.

## 2. Reading a per-strain signal inside a community

- **per-strain qPCR** [baseline]: direct per-strain counts, when the study reports them.
- **deconvolution from community OD**, or **relative abundance from sequencing**: when they accompany the data.

**Proposed default (Craig): per-strain qPCR as the study reports it, no deconvolution by default.** A study
without a per-strain signal is skipped and reported, not inferred.

## 4. Significance and uncertainty

- **qualitative point estimate** [baseline]: one number per edge, `significance` null, no error bar.
- **a replicate-based test** (Welch or Mann-Whitney across bioreplicates): needs replicate-level values.
- **an effect size with multiple-testing correction** (FDR) across all pairs.

The baseline claims no p-value, which is honest, but it also propagates no uncertainty at all: the number
on an edge could rest on one replicate or ten and looks the same. The replicate-aware code already exists
in `interaction.py`; wiring it through so an edge carries a standard error and a replicate count (three new
fields in the schema) is mostly plumbing, not new science.

**Proposed default (Craig): qualitative now, then wire the replicate standard error and count through, then
adopt a test.** The viewer already shows magnitude as a coarse band rather than false precision while an
edge is qualitative. Which test to adopt is Karoline's call.

## 5. Scope of the co-cultures

- **pairwise, two-member only** [baseline]: a clean attribution of who affected whom.
- **larger communities**: needs a rule for attributing a per-strain change to a specific partner.

Study SMGDB00000007 is mostly pairwise and works with the baseline today; SMGDB00000008 is a
species-deletion design with 13 to 14 member consortia, so the pairwise baseline skips all of it and the
network is empty. Supporting that class of study is one of the higher-value builds (see setting 9). Worth
stating for scale: pairwise plus qPCR-only is a narrow slice of mGrowthDB, so few studies yield a
non-empty network today.

**Proposed default (Craig): pairwise.** Clean attribution for the first networks; larger communities
arrive through setting 9 rather than by changing this default.

## 6. Technique mismatch

The baseline records the monoculture and co-culture techniques on every edge and flags a mismatch. A log
ratio only cancels a shared scale when both sides share a modality. When they do not (qPCR over OD), a
systematic offset between the two instruments enters the ratio, so the magnitude is provisional and, near
the neutral band, the sign itself can move. Direction is not fully dependable for a mismatched edge.

**Proposed default (Craig): flag on every edge, and treat a mismatched edge's sign as provisional near the
band.** Options to build: restrict a published network to matched-technique comparisons, calibrate an
offset between techniques, or widen the neutral band for mismatched edges.

## 7. Taxonomic identity and aggregation

Two questions: at what rank is a node defined, and what stable identifier does it carry.

- **genus and species, name-keyed** [baseline today]: `_gs` collapses a strain name to genus and species,
  so strains of one species merge into one node and the monoculture lookup keeps the last one seen.
- **strain**: the data's native resolution, nothing merged.
- **an NCBI taxid (or GTDB) on every node**: the identifier a downstream layer joins on.

The name-keyed default silently pools strains, which for a log ratio is an averaging-of-ratios hazard (it
can move a magnitude or a sign). Just as important for the shared goal: microbetag annotates by NCBI
taxonomy, and Cytoscape's Merge aligns nodes on a shared column. A crossfeed node named
`faecalibacterium prausnitzii` will not match a taxid, so the three evidence layers do not overlay today,
they duplicate. mGrowthDB exposes strain NCBI ids; the deriver currently reads only the name and drops the
id.

**Proposed default (Craig): carry an NCBI taxid on every node, and pick one merge rank (species is the
pragmatic choice for overlaying with microbetag).** If we keep any strain-to-species rollup, it needs a
stated rule (combine per-strain strengths by inverse-variance or replicate weight, never a raw average of
ratios). This is the setting that unlocks the STRING-style overlay, so it is worth doing early.

## 8. Environment and medium

- **keep all conditions, tag each edge with its condition** [baseline]: every edge carries its `condition`.
- **restrict to one medium or condition**: a single-environment network.

Restriction is not available yet: mGrowthDB does not carry structured enough environment metadata to select
on, as Karoline noted. The viewer shows this control disabled for that reason.

**Proposed default (Craig): keep all conditions and tag each edge; do not average across media.** Add the
restriction when the metadata supports it.

## 9. Drop-out (leave-one-out) communities

Deletion designs grow a community with one member removed and read the effect on the rest. They carry
interaction information the pairwise baseline (setting 5) skips.

- **exclude** [baseline]: the pairwise default ignores them.
- **include**: an opt-in deriver that attributes a per-strain change under a deletion to the removed member,
  which recovers studies like SMGDB00000008.

**Proposed default (Craig): exclude from the default network, support as an opt-in deriver.** One of the
higher-value builds, since it unlocks a class of real studies without changing the pairwise default.

## 10. Edge thresholds: strength and supporting studies

- **minimum interaction strength**: hide edges below a magnitude.
- **minimum number of supporting studies**: hide edges seen in fewer than N studies.

The strength floor works today. The supporting-studies floor does not mean much yet: edges for one
interaction are not merged, so every edge has exactly one study id, and raising the floor above one empties
the network rather than selecting well-replicated edges. A merge step (one edge per interaction, unioned
study ids, combined strength) has to come first.

**Proposed default (Craig): minimum strength 0 and minimum supporting studies 1, filtered in the viewer;
build edge merging, then a published network can carry a strength floor and a replication floor.** Hiding
data at derivation time is harder to undo than filtering a view.

## 11. Minimum time points

A growth rate is only as good as the curve behind it. The baseline does not fit the rate; it reads the
value mGrowthDB reports, so a crossfeed time-point count does not apply to what ships.

**Proposed default (Craig): carry the fit quality mGrowthDB reports (points used, rate error) onto the edge
and gate on that.** If we ever fit rates in-tool, the floor is several points spanning exponential phase
with a reported fit error, not two points, which define a line with no residual.

## 12. Chemostats and serial dilutions

Continuous culture and serial dilution are different growth regimes from a batch curve.

- **flag and keep separate** [baseline intent]: mark the regime and do not pool it with batch runs.
- **include with batch**, or **exclude**.

**Proposed default (Craig): flag and keep separate from batch.** The regimes are not obviously comparable,
so pooling them is a decision to make on purpose.

## 13. Output format

- **JSON** [baseline]: the canonical neutral network, what the whole pipeline reads and writes.
- **GraphML on demand**: the same network for Cytoscape, igraph, networkx, or Gephi (`--format graphml`).

**Proposed default (Craig): JSON canonical, GraphML on demand.** Both exist today; the viewer writes the
same GraphML the CLI does.

## Open decisions

This is the single place where open method and format questions are collected, so Karoline and Craig
can settle several at once. Agents add a question here (with the options, a proposed default, and the
issue it came from) instead of deciding it; a settled item moves to "Decisions" in
[docs/agents/NOTES.md](agents/NOTES.md) with the date and who decided.

1. **Status of the replicate set comparison** (#3). `crossfeed.interaction.interaction_strength`
   compares a species' growth with and without a partner as mean(log2 property with) minus mean(log2
   property without), with sd and se from the per-set log2 spread, over the area under the curve or the
   maximal abundance. Specified by Karoline and merged as provisional. Options: adopt it as the agreed
   comparison (settings 1 and 3 above), or keep it provisional. Proposed default: adopt it, and keep the
   growth metric (setting 1) open for growth rates.
   SETTLED 2026-09-19 (Karoline); recorded in "Decisions" in [docs/agents/NOTES.md](agents/NOTES.md).
   Adopted: the pipeline derives through this comparison (#34).
2. **Arcs from drop-out communities** (#10). Comparing the full community with the community without R
   gives an arc R to X that is not necessarily direct (R can act through a third species); strictly a
   hyper-arc. Karoline's position: keep these arcs, labeled by evidence, with the community recorded.
   To confirm with Craig. This addresses setting 5 and study SMGDB00000008.
   Status 2026-09-18: #16 merged `interaction.dropout_interaction_strengths`, a complete and tested
   implementation of the comparison. Emitting these arcs is not a change of default, though: that function
   takes `Replicate` objects, `derive.py` works from mGrowthDB experiment dicts, and nothing in `src/`
   builds a `Replicate`, so there is no path from the API to these arcs. Saying yes here commissions that
   adapter, and the adapter routes the pipeline through `interaction.py`, which also settles items 1, 11
   and 12. See item 15, which is the reason all four travel together.
   Status 2026-09-20: the adapter landed in #38, so the blocker named above is gone and these arcs are
   now reachable.
   SETTLED 2026-09-20 (Craig); recorded in "Decisions" in [docs/agents/NOTES.md](agents/NOTES.md).
   Drop-out arcs enter the default network, labeled by evidence with the community recorded, as the
   default value of a user setting. Karoline's own words put it among the advanced settings (2026-09-18):
   the interface should offer "whether or not to include drop-out communities" among choices that "can be
   given sensible default values and hidden in a window that only appears when an Advanced settings button
   is clicked", under her general rule that "unless you have an argument against a particular
   implementation, I'd leave it as a user choice in advanced settings. We can perhaps put our votes on
   defaults in METHOD_NOTES." So the setting exists either way; Craig's decision is that its default is
   include.
   RESOLVED 2026-09-21: Karoline's own words, given when she specified the drop-out feature on
   2026-09-17 and confirmed as her answer here: "I'd still like to include these arcs, because they are
   still informative, but any arcs in the interaction network coming from drop-out communities should be
   labeled as such." That is inclusion in the network with a label, which is what Craig's decision on the
   default does, so the two agree. The earlier line attributing "keep these arcs" to her was her agent's
   paraphrase rather than a quotation, which is why it was queried on #34; the paraphrase turned out to
   carry her meaning, and the quotation now stands in its place.
   Implementation: routing a drop-out design (a full community plus experiments each missing one member)
   to `dropout_interaction_strengths` is claimed on the KU Leuven side under #34. Neither deriver does it
   yet: `BaselineDeriver` skips experiments with more than two members, and so does the `ReplicateDeriver`
   arriving in #40.
3. **Dependence between arcs** (#10, #3). Arcs to the same target from different drop-outs reuse the
   full community replicates, and the two values of a pair reuse the same co-culture replicates, so they
   are not independent. Options: document it only (current), or model the covariance when significance
   is tested. Proposed default: document it now, decide together with item 10.
   Status 2026-09-21: item 10 has been settled (Welch's t-test with Benjamini-Hochberg) without this one,
   which it had reserved. Settling this decides whether that correction suits the dependence actually
   present, so it is no longer only documentation.
4. **New optional edge fields in the neutral format** (#11). `evidence` (`biculture` for mono versus
   bi-culture, direct; `dropout`, possibly indirect) and `community` (members of the full community).
   Backward compatible, but a change to the contract downstream tools read. Proposed default: accept.
   SETTLED 2026-09-18 (Craig, on merging #17); recorded in "Decisions" in
   [docs/agents/NOTES.md](agents/NOTES.md).
5. **Zero growth and detection limits** (#16). Decided by Karoline: a species that grows only with the
   source present is an obligate commensal or mutualist, reported as outcome `obligate` (and `abolished`
   for growth only without the source), not as an error. Still open: how such arcs appear in the network
   (proposed default: effect `facilitation` or `inhibition` with a null strength and the outcome recorded),
   and what counts as no growth in real data, where values rarely reach exactly zero (options: a
   detection limit per technique, a minimum increase over the first time point, or a pseudocount).
   SETTLED 2026-09-19 (Karoline); recorded in "Decisions" in [docs/agents/NOTES.md](agents/NOTES.md). No
   growth is a test across replicates comparing start abundance to maximum abundance, not a
   detection limit. Still ours to pick: which test and its alpha (the same choice as item 10), and what
   to do when a set has no replicates to test with.
6. **Whether crossfeed ships a user interface at all** (#18). Karoline asked for a local page where a
   person types species names and gets their interactions, with settings hidden behind an "Advanced
   settings" button. Built as a standard-library server on 127.0.0.1 with no JavaScript, so the promise
   of no runtime dependencies and nothing to host holds. The question for the maintainers: does a page
   that shows provisional results to people who do not read the method notes belong in the repository
   now, or after the method is settled? The page labels every result provisional and cites each study.
   Proposed default: keep it, since it is the fastest way for the collaboration to look at real data.
   Status 2026-09-18: #22 merged that page, and #29 added `gui/index.html`, a self-contained viewer for a
   network that has already been derived. They answer different questions and carry very different
   exposure: `crossfeed gui` takes a species name from anyone and derives live against mGrowthDB with the
   provisional baseline, while `gui/index.html` only draws a file its reader already produced and chose to
   open. The concern in this item lands on the first and barely touches the second, so the two are worth
   deciding separately. What argues against keeping both as they stand is not disk space but drift: the
   settings menu is now hand-maintained in three places (`gui.py`, `gui/index.html`, and this document),
   so a changed default has three chances to go stale. Proposed default: keep both, say in one README
   sentence which question each answers, and give the settings menu one source in code that both
   interfaces render.
7. **Strain-level or species-level identity** (#23). Karoline: arcs should be reported per strain and
   labeled with the strain name, for all strains of a species that have data. Today nodes are keyed by
   genus and species, which pools strains and, because names change, splits one strain across nodes
   (taxon 411483 appears as Faecalibacterium prausnitzii A2-165 and as Faecalibacterium duncaniae A2-165).
   Proposed default: key nodes by NCBI taxon id, name them with the strain name, keep the species-level id
   as an attribute, and match monoculture to co-culture by id. This changes how the provisional baseline
   matches strains and what the emitted network looks like. mGrowthDB entries are being corrected upstream
   to always point to strains rather than species.
   Status 2026-09-18: #21 merged the resolver from names to taxon ids, which is the groundwork; nodes are
   still keyed by genus and species. Two things the proposal needs before it can be implemented, both
   raised by review rather than by the data:
   (a) **Rank is not uniform.** 411483 is a strain-rank id, 853 is the species-rank id for the same
   organism, and mGrowthDB holds both kinds today (the note that entries are being corrected upstream to
   point at strains is the admission that today they are not). Keying on "the taxon id" therefore still
   splits one organism across nodes, just at a different place. Proposed amendment: every node carries
   `taxon_id`, a `rank` saying what that id is, and a `species_taxon_id`, so item 8's shared merge key
   always exists even when the record is strain-rank, and a consumer can see which it got.
   (b) **`species_taxon_id` collides with the standing rule that names resolve through mGrowthDB and
   never by querying NCBI.** Getting the species-rank ancestor of a strain-rank id is a taxonomy lookup.
   `taxonomy.species_index` sidesteps it today by bucketing on the genus and species of the *name*, which
   is the unstable thing this item exists to escape. Open: does mGrowthDB expose a species-rank id
   alongside `NCBId`? If it does, use it. If not, the species key is derived from the name, and the node
   should say so rather than imply a taxonomy lookup happened.
   Separately, the pooling this item would fix is worse than pooling: `derive.py` keeps the last
   monoculture seen per genus and species key, so additional strains are discarded with no entry in
   `skipped`. That is a defect to fix whichever way this item is settled.
   SETTLED 2026-09-19 (Karoline); recorded in "Decisions" in [docs/agents/NOTES.md](agents/NOTES.md). Part
   (b) is answered: mGrowthDB will not expose species-rank or higher taxa, so a node carries
   `taxon_id` and a `rank`, and the species key comes from elsewhere (item 8). The pooling defect noted
   just above was fixed in #33, which reports the collision instead of passing it silently.
8. **The node key for merging with other tools** (#25, microbetag). Merging experimentally confirmed
   interactions with microbetag networks as a multigraph needs matching node identifiers but not matching
   edge identifiers. Proposed default: the species-level NCBI taxon id as the shared key, with the strain
   id kept alongside, and every edge stating whether it is experimental or predicted so the two are never
   blurred. Open: whether crossfeed does the merging at all or only produces networks, and whether a
   direct route into Cytoscape sits well with the neutral format being tool-neutral.
   SETTLED 2026-09-19 (Karoline); recorded in "Decisions" in [docs/agents/NOTES.md](agents/NOTES.md). The
   shared key is derived from the genus and species of the name, and the node says so rather than
   implying a taxonomy lookup happened; matching at strain rank stays the guarantee for any consumer, and
   a cached NCBI lookup is the upgrade if the mGrowthDB-only naming rule is relaxed. Open for Haris:
   whether microbetag can meet crossfeed at strain rank.
9. **Shipping desktop binaries** (#26). Karoline: the typical user runs Windows and has no command line
   experience, so installing Python, Git, and a virtual environment is out of reach. A CI-built,
   double-click Windows executable would remove that. The commitments: an unsigned build triggers a
   SmartScreen warning (a code-signing certificate costs money and institutional paperwork), PyInstaller
   output draws antivirus false positives, and every release needs a build, a test on real Windows, and
   support for people new to software. Proposed default: ship it unsigned, explain the warning in the
   README, and revisit if a certificate becomes available. A lighter step that needs no decision is a
   PyPI release (#27).
10. **Significance testing** (setting 4). Still open: which test on the per-replicate log2 values (for
   example Welch's t-test), and whether to correct for multiple testing across arcs.
   DEFERRED by Karoline 2026-09-19 until the settled items have landed. Note that this and item 5's
   no-growth test are the same choice of test and alpha.
   SETTLED 2026-09-21 (Karoline). Her words: "let's drop the significance test as a decision-making tool
   but keep its result in an edge attribute, since a significant result supports an edge (whereas a
   non-significant result is not informative)", and "when we apply a statistical test, I think it's
   better to include multiple testing correction." So Welch's two-sided t-test on the per-replicate log2
   values, `p_value` raw and `significance` Benjamini-Hochberg adjusted over every comparison tested in one
   derivation; presence stays decided by mean plus or minus sd (item 19).
11. **The growth metric and the comparison are one coupled choice** (raised by the Syntropa-side review,
   2026-09-18). A log ratio suits an extensive quantity (AUC, yield, biomass), where doubling is
   meaningful and the value stays away from zero. On a growth rate it is unstable: when the monoculture
   rate is small the denominator drives the ratio to a large magnitude or flips its sign, exactly where an
   interaction looks strongest. The baseline ships growthRate with log2(co over mono). Options: move the
   default metric to AUC and keep the log ratio, or keep growthRate and compare by a difference. Proposed
   default: AUC with the log ratio, since the log ratio is already implemented and AUC is what it suits;
   growthRate travelling better across techniques is the reason to weigh the difference instead. Settings
   1 and 3.
   SETTLED 2026-09-19 (Karoline); recorded in "Decisions" in [docs/agents/NOTES.md](agents/NOTES.md). Both
   metrics ship, AUC the default, `max` selectable, and growth rate joins once it has a stated
   rule (#41).
12. **The shipped baseline propagates no uncertainty** (raised by the Syntropa-side review, 2026-09-18).
   `interaction.py` computes sd and se from replicate log2 values, but the network the pipeline emits
   comes from `derive.py`, which compares single scalar values and sets significance to null, so an edge
   carries no error bar and no replicate count. Options: route the baseline through the replicate-aware
   path and add se, n_co and n_mono to the schema, or state plainly that the baseline is a point estimate.
   Proposed default: wire the replicate path through, then settle the test in item 10. Setting 4.
   SETTLED 2026-09-19 (Karoline); recorded in "Decisions" in [docs/agents/NOTES.md](agents/NOTES.md).
   Wired: every edge carries a standard error and the replicate counts (#36).
13. **How far to trust a mismatched-technique sign** (raised by the Syntropa-side review, 2026-09-18). A
   log ratio only cancels a shared scale when both sides share a modality. In the FP/BH study the
   monoculture is flow cytometry or OD and the per-strain co-culture is qPCR, so a systematic offset
   between instruments enters the ratio and, near the neutral band, can move the sign and not only the
   magnitude. Options: flag only (current), restrict a published network to matched-technique comparisons,
   calibrate an offset between techniques, or widen the neutral band for mismatched edges. Proposed
   default: flag, and treat a mismatched edge's sign as provisional near the band. Setting 6.
   DEFERRED by Karoline 2026-09-19 until the settled items have landed.
14. **Merging edges per interaction, before a replication floor can mean anything** (raised by the
   Syntropa-side review, 2026-09-18). Records for one interaction are never merged, so each condition and
   study is its own edge and every edge carries exactly one study id. A minimum-supporting-studies
   threshold above one therefore empties a network rather than selecting well-replicated edges. Options:
   merge records for the same interaction (unioning study ids and combining strengths by a stated rule),
   or drop the threshold until merging exists. Proposed default: build the merge, after which a
   replication floor becomes meaningful. Setting 10.
   DEFERRED by Karoline 2026-09-19 until the settled items have landed.

15. **The repository holds two implementations of the comparison, and the pipeline reaches the weaker one**
   (raised by the Syntropa-side review, 2026-09-18). `interaction.py` with `growth.py` is the comparison
   Karoline specified: replicate sets summarized on the log2 scale, AUC by default, sd and se, explicit
   `obligate`, `abolished` and `no_growth` outcomes, per-replicate values kept for a later test. It is
   tested against hand-computed examples and it is the method of record. `derive.py` is the provisional
   placeholder written to make the seam run: single scalar values, growth rate, log2 of a ratio, no
   uncertainty, no outcomes. The pipeline, the CLI and both interfaces reach only `derive.py`, and a
   `Replicate` is constructed nowhere outside the tests. So the tool ships the placeholder and the agreed
   method sits unreachable beside it, and the two disagree on the metric, on the comparison, and on what a
   node is. This is why items 1, 2, 11 and 12 cannot be answered one at a time: each of them is a request
   to reach `interaction.py`. Options: build the mGrowthDB to `Replicate` adapter and let `derive.py`
   shrink to that adapter behind the existing `Deriver` seam, or state in the README that the shipped
   method and the specified method are different and which one a given output used. Proposed default: build
   the adapter. It retires the placeholder, and it is the single piece of work that settles four items.
   Anything that adds a third comparison, including the cheaper-looking route of computing drop-out arcs
   inside `derive.py`, makes this worse and should be refused.
   SETTLED 2026-09-19 (Karoline); recorded in "Decisions" in [docs/agents/NOTES.md](agents/NOTES.md).
   Karoline: "go with your recommendation". Built as #38 (the adapter) and #40 (the deriver), so the
   placeholder retires.
16. **How hard crossfeed is allowed to lean on mGrowthDB** (raised by the Syntropa-side review,
   2026-09-18). `taxonomy.species_index` builds its name index by walking study ids from 1 upward until
   five consecutive ids are absent, capped at 500, and `crossfeed gui` calls it on a cold cache before it
   can answer the first query. That is a large number of requests against someone else's service for one
   person typing one species name. Responses are cached, so this is a cold-start cost rather than a
   per-query one. Open: is that acceptable to the people who run mGrowthDB, and should crossfeed ship a
   prebuilt index with releases, refreshed deliberately, instead of crawling on demand. This is a
   courtesy question toward the database the collaboration depends on, so it wants an answer from them
   rather than a default from us.
17. **Outlier replicates need a stated rule** (#39, found in real data 2026-09-19). Running the specified
   comparison on SMGDB00000004 gave B. hydrogenotrophica a standard error of 3.5 on the log2 scale, which
   traces to one replicate: BH_14's qPCR trace (context 3465) holds two consecutive points at 5.264e13
   cells/mL between neighbors of 1.06e8 and 4.84e8. The community traces in the study's visualizer look
   fine; the artifact is in the per-strain qPCR trace the comparison reads. With BH_14 left out the three
   metrics agree (AUC +1.29 se 0.12, max +1.15 se 0.17, growth rate +0.33 se 0.11, all facilitation), and
   the biology points the same way: F. prausnitzii produces CO2 and formate that B. hydrogenotrophica
   consumes. SETTLED 2026-09-19 (Karoline): flag such replicates, never drop them silently, with the
   factor an advanced setting. Growth rate is the more robust metric under an artifact like this, which is
   part of why item 11 ships both.

18. **Query scope, whether a species query pulls in its relatives** (setting 14, unregistered until
   2026-09-21). Karoline's advanced-settings list names "whether to include other strains of the same
   species or other species of the same genus [a whole can of worms]", and it had no setting and no
   register item. It is not item 7: item 7 is how a node is keyed once derived, this is what a query
   returns before anything is derived. `taxonomy.resolve_species` already returns every taxon id
   mGrowthDB holds under a typed genus and species, so the strain half is partly built and undocumented
   as a choice. Options: the typed strain only, all strains of the species, or all species of the genus.
   No proposed default yet; Karoline called it a can of worms and she is right, because widening the
   query silently changes which arcs a person sees.
19. **How an edge's effect label relates to its spread** (raised by the Syntropa-side review on #40,
   2026-09-20). The label was decided from the mean against a fixed 0.25 band while the spread computed
   alongside it went unread, so on the flagship study six of ten edges carried a direction their own
   spread did not support.
   SETTLED 2026-09-21 (Karoline). The label follows the spread, using the standard deviation rather than
   the standard error, because sd describes the spread of a single comparison and does not shrink as
   replicates are added, so the test cannot be passed by running more of them. Her words: "if both mean
   and standard deviation are in the positive range, then it's facilitation and if in the negative range,
   then inhibition. If the standard deviation crosses the sign, I suggest to label the edge as
   unreliable, with the sign assigned from the mean". She then separated two things a crossing interval
   could mean: "neutral is the absence of an interaction. However, we need to differentiate carefully
   between edges with low quality and absence of an interaction. So an absence of an interaction is an
   edge that has no quality issues but the sd crosses the sign or better, a robust statistical test on the
   selected mono- and co-culture growth curve characteristic is not significant."

   | quality flags | mean plus or minus sd | effect |
   | --- | --- | --- |
   | none | entirely above zero | facilitation |
   | none | entirely below zero | inhibition |
   | none | crosses zero | neutral, meaning no interaction |
   | any | any | the sign of the mean, flagged low quality |

   The sd rule stands in for a statistical test until item 10 settles one, and is replaced by the test in
   the neutral row when it does. The fixed 0.25 band retires with `BaselineDeriver`: neutral is defined by
   the data, not by a constant. OPEN within this item: `obligate` and `abolished` carry no mean and no sd
   by construction, so no row above can place them, and the Syntropa side has proposed a fifth row
   showing them by default with the effect taken from the outcome (see #40).
20. **Edge quality as an attribute** (Karoline, 2026-09-21). Rather than drop a weak edge or silently
   keep it, an edge carries a list of quality flags saying what is wrong with it, so a consumer can filter
   on the specific problem. Her words: "keep edges computed on a single replicate but flag them as
   somewhat less reliable. So that means we need an edge quality attribute ... If we record these
   different issues in the quality attribute, a user can filter differentially later."
   SETTLED 2026-09-21: accepted by Karoline as the method and by Craig as a change to the neutral format,
   which it is. `quality` and `sd` join the edge as optional fields, backward compatible in the way
   `evidence` and `community` were (item 4), with the schema regenerated from the model. Flags in view so
   far: a single replicate, a spread crossing the sign, an outlier replicate in the set (#39), strains of
   one species pooled into one monoculture set (until #23), and a non-batch cultivation mode (#42).
21. **Which edges a network shows by default** (Karoline, 2026-09-21). Her words: "The user should be
   able to display 'neutral' and/or 'low-quality' edges at wish, but I suggest to filter out both by
   default."
   SETTLED 2026-09-21: two display settings, both off by default, in the command line and both interfaces.
   The derivation computes every edge and the filter applies at output, so nothing is lost, only hidden,
   and the network's `meta` records which filters were applied so a reader of a file knows what was left
   out. Note for item 10: a threshold on strength has to treat a null strength as not comparable rather
   than as zero, or an `obligate` edge disappears at that filter instead of this one.

Once a default lands as a `Deriver`, the FP/BH slice reruns against it unchanged, so settling these does
not cost rework.
