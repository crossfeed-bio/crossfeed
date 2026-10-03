# Derivation method: settings and agreed defaults

mGrowthDB serves growth curves, not interactions. Turning growth into a directed, condition-specific
interaction is a scientific choice, and it belongs to the collaboration (K. Faust, H. Zafeiropoulos), not
to this code.

Following Karoline's suggestion, the choices below are user-configurable settings, not one fixed method.
Each has a sensible default. A user changes any of them by selecting a `Deriver` and its options on the
command line or in the local page's advanced settings (`crossfeed gui`), which show the same settings
with the same defaults, and every network records the ones it was made with. This note records the defaults. The "Proposed default" line
under each setting is Craig's opening vote, so there is something concrete to react to. Karoline and Haris
weigh in, we settle each default together, and the settled value ships as the default.

## What the default derivation does today

**Status 2026-09-21.** `ReplicateDeriver` is the default for a live derivation (#40). It reads each
replicate's measured curve through `crossfeed.adapter` (#38) and compares replicate sets with
`crossfeed.interaction.interaction_strength`, the comparison Karoline specified, so the defaults settled
below are shipped behavior rather than intentions. Every edge carries its mean, `sd`, `se`, replicate
counts, outcome, metric, `quality` flags and `notes`.

- **Area under the curve by default**, `max` selectable with `--metric` (setting 1).
- **Presence follows the spread, through the absence threshold k** (option B, Karoline, 2026-09-21): a
  comparison's `status` is `absent` when |log2 mean| < k × sd and `present` otherwise, default k = 1 (the
  mean ± sd rule), k = 0 marking nothing absent. There is no "neutral edge", the absence of an edge is
  what a sub-threshold comparison is. Every comparison carries `status`, `weight` (|log2 mean|) and
  `effect_over_sd` (|log2 mean| / sd). A sub-threshold one is reported in the result and the report but
  **left out of every output** unless `--include-absent` is given (amended 2026-10-03, Karoline: "The arc
  number reported in Cytoscape is not identical to the arc number we see because of hidden arcs"), so the
  page, a file and Cytoscape all count the same arcs; with the setting on, `effect_over_sd` still lets a
  reader move the threshold in Cytoscape (item 19). Karoline asked for this to be carefully documented;
  the README's output-format section is the reference.
- **Low-quality edges are computed and hidden**, with `--include-low-quality` to show them and
  `meta.hidden` counting what was left out (item 21). Single-replicate edges are shown by default and
  marked in the Cytoscape style (Karoline, on #62).
- **A statistical test is reported, never used to decide** (Karoline, 2026-09-21): Welch's t-test on the
  per-replicate log2 values, `p_value` raw, `q_value` adjusted (Benjamini-Hochberg by default,
  Benjamini-Yekutieli as a setting) over every comparison tested in one derivation, named in
  `meta.statistics` (item 10), and `significance` = -log10(`q_value`), so that larger means stronger
  evidence (Karoline, 2026-10-03).
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

The method as it runs today (2026-09-27), with where each choice was settled. The sections below are the
history of how each was decided.

1. Growth metric: **AUC** (item 11), `max` selectable, and the growth rate selectable (#41): easylinear by
   default, as mGrowthDB computes its reported rates, window 5; a guarded Baranyi fit as the alternative
2. Per-strain signal: **a per-strain measurement context as mGrowthDB records it** (subject strain); a
   species is compared only with itself measured by the same technique (item 23)
3. Mono versus co comparison: **mean log2 over replicate sets** (items 1, 12), after the no-growth rule
   (item 5: paired test, or a rise of 1.5 times)
4. Significance and uncertainty: **sd, se and replicate counts on every edge**; presence follows the spread
   through the absence threshold k (item 15, default 1); Welch's t-test with Benjamini-Hochberg (or
   Benjamini-Yekutieli) is reported as support and decides nothing (item 10)
5. Designs: **two-member co-cultures and drop-out communities** (item 2), both included by default
6. Technique: **the same species-identifying technique on both sides**, or the pair is skipped (item 23)
7. Taxonomic identity: **strains keyed by NCBI taxon id, named by their current name** (#23, #24); a
   strain without an id falls back to genus and species, where pooled strains are flagged `strains_pooled`
8. Environment and medium: **all recorded conditions kept, one edge per experiment**; experiments pool only
   when their recorded conditions and descriptions agree (items 22, #47); filtering by environment cannot
   be built on mGrowthDB's metadata (Karoline, #61)
9. Drop-out communities: **included, labeled by evidence** (settled by Craig 2026-09-20; built, #47)
10. Edge thresholds: **no strength floor**; merging parallel arcs is a setting, off by default, and a
    minimum-supporting-studies filter applies to merged arcs (item 14)
11. Minimum time points: **a curve needs its points for the metric** (easylinear: window plus one); no
    fit-quality gate on mGrowthDB's values, which are not read
12. Chemostats and serial dilutions: **left out by default with auc or a growth rate** (flagged
    `non_batch` when asked for anyway), **derived with max**, which that mode suits, marked
    `continuous_culture` (#42, amended 2026-10-03)
13. Output format: **JSON canonical, GraphML on demand**, and a report
14. Query scope: **a species name resolves to all its strains** in mGrowthDB, and only interactions between
    the species entered are shown unless unticked
15. Absences of interaction: **decided by threshold k, default 1; reported in the result and the report,
    and left out of every output unless asked** (settled 2026-09-21 as exported and hidden by the display;
    amended 2026-10-03 so that one number holds everywhere, `--include-absent` to export them)
16. Show low-quality edges: **off** (settled 2026-09-21); computed, flagged, and hidden; single-replicate
    edges are shown and marked

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

Craig's first proposal was to exclude them from the default network behind an opt-in deriver. SETTLED
2026-09-20 and 2026-09-21 (register item 2): include them by default, labeled `evidence: dropout`, with a
setting to leave them out. Built in #47; the rules Karoline set for it are in "Decisions" in
[docs/agents/NOTES.md](agents/NOTES.md).

## 10. Edge thresholds: strength and supporting studies

- **minimum interaction strength**: hide edges below a magnitude.
- **minimum number of supporting studies**: hide edges seen in fewer than N studies.

(Status 2026-09-27: no strength floor is offered. Merging parallel arcs is built, as a setting off by
default, and the supporting-studies floor applies to merged arcs; see item 14.) At the time of writing:
the supporting-studies floor did not mean much, since edges for one interaction were not merged, so every
edge had exactly one study id and raising the floor above one emptied the network. A merge step had to
come first.

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

BUILT 2026-09-27 (#42, Karoline): only batch is derived by default; other modes, and a missing mode, are
reported with the mode and left out. `--include-non-batch` derives them with the edges flagged
`non_batch`, which is hidden by default like the other quality flags. Every edge carries
`cultivation_mode`.

AMENDED 2026-10-03 (Karoline): "right now, we don't use data when they are from chemostat. But we can, when
the growth curve property is max. I think the no-chemostat filter is too harsh, we should allow it when max
is the growth property being compared." So continuous culture is derived by default with `--metric max`,
and those arcs carry the caution `continuous_culture` and are shown; with `auc` or a growth rate they are
still left out unless `--include-non-batch` is given, and then they keep the `non_batch` quality flag. The
reason a run gives names the way out. A comparison never mixes modes, since `conditions` carries the
cultivation mode. Measured when it was built: no study in mGrowthDB today has a non-batch pairwise or
drop-out design, so this changes no current network; SMGDB00000001, 5 and 11 are single large communities
with no leave-one-out partners.

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
   SETTLED 2026-09-21 (Karoline, on #47): document it, keep Benjamini-Hochberg as the default with
   Benjamini-Yekutieli as a setting, and make the dependence visible on each edge. Her words: "such arcs
   should have an attribute whose value is the experiment of origin and a flag that they come from a
   drop-out experiment". Edges carry `experiments` and `evidence`; arcs sharing an experiment share
   replicates.
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
   SETTLED 2026-09-27 (Karoline, on #68): "yes to all 3, as long as the maximum in the paired test can
   come from different time points (since the time of maximum abundance may vary across replicates)."
   The three: keep the twofold half at a factor of 2, make both numbers settings recorded in the network,
   and test with a paired test. `crossfeed.interaction.grew` takes one rise per replicate,
   log2(maximum / abundance at the first time point), each maximum at that replicate's own time, and
   applies it before any ratio. The set has grown when a paired two-sided t-test finds the mean rise above
   zero at `NO_GROWTH_ALPHA` (0.05), or when the mean rise reaches log2(`NO_GROWTH_FACTOR`) (a geometric
   mean of the ratios reaching the factor). The default factor is 1.5 (Karoline, later the same day, her
   words: "I'd put the factor (which defines growth) as an advanced option. the default can be medium
   (1.5) and it can be made more stringent by the user (e.g. set to 2)."). At 2, two near-twofold rises
   became strong claims (SMGDB00000013 Ochrobactrum to Comamonas abolished, SMGDB00000008 B. finegoldii
   to B. thetaiotaomicron obligate); at 1.5 both stay quantified. Pairing each maximum with its own start removes the spread between
   inocula, which the earlier Welch test on unrelated samples counted as noise. Below two replicates the
   test cannot run and the set counts as grown when its maximum exceeds its start. Why the factor: with
   two or three replicates a real rise often misses significance, and the test alone made 10 of
   SMGDB00000004's 20 edges obligate or abolished, and 8 of SMGDB00000013's 9. `meta.no_growth` records
   both numbers and the obligate and abolished counts (Craig's agent, on #68).
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
   BUILT 2026-09-21 (#23, Karoline: "taxon id should be strain level. That requires a node label with the
   name of the strain to keep the network readable"). Nodes are keyed `ncbi:<taxon id>` and named with the
   strain name, with `species` (from the name, item 8) and `identity` as attributes. No `rank`: mGrowthDB
   does not report one, and inferring it would be a taxonomy lookup. An id that a study gives to strains
   with different designations falls back to genus and species (identity `name`) and is reported.
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
   SmartScreen warning, PyInstaller output draws antivirus false positives, and every release needs a
   build, a test on real Windows, and support for people new to software. A lighter step that needs no
   decision is a PyPI release (#27).
   Corrected 2026-09-21, after a review of the actual mechanics (#26). This item previously said a
   code-signing certificate "costs money and institutional paperwork" and that the decision should be
   revisited "if a certificate becomes available". Both are wrong:
   (a) **No purchased certificate removes the warning.** Since 2024 Microsoft treats OV and EV
   certificates alike, so paying a premium for EV to clear SmartScreen is not justified.
   (b) **But signing still matters, for two reasons.** Reputation has two signals, the publisher
   certificate and the file hash, and "reputation cannot transfer from previous versions unless both
   were signed using the same publisher identity". So a signed publisher accumulates reputation across
   releases while an unsigned build restarts from zero at every release, permanently. Separately, Smart
   App Control on Windows 11 blocks unsigned executables that lack positive reputation, rather than
   warning about them, so for those users unsigned is not a warning to click through.
   (c) **Signing is free for this project.** The SignPath Foundation signs open-source projects at no
   cost; Apache-2.0 qualifies and it verifies the repository rather than a person. It also cuts the
   antivirus false positives PyInstaller output attracts. Two conditions shape the order: a release must
   already exist in the form to be signed, so shipping unsigned is the prerequisite rather than a
   compromise; and the certificate is issued to the Foundation, which becomes the publisher a user sees.
   (d) **The Microsoft Store removes the warning outright, and is also free.** Microsoft's own guidance
   leads with it: a Store-distributed app is signed by a Microsoft certificate and is never subject to a
   SmartScreen download warning. Registration fees were dropped for individuals in 2025 and for
   companies in 2026. Packaged as MSIX, Microsoft hosts the binary, signs it, and delivers updates, and
   the PyInstaller antivirus problem goes away with the packaging.
   Proposed default (Craig's side, awaiting his ruling): three steps, each costing nothing. Ship
   unsigned now, since SignPath requires an existing release; say what Windows will do in the README and
   on the release page; add SignPath signing once a release exists; and move to the Store when the
   method is settled enough to list. Never buy a commercial certificate. Azure Artifact Signing, about
   ten dollars a month, is a fallback only if SignPath eligibility fails.
   What this turns on is not cost. A Store listing is far more public than a repository release, which
   sharpens item 6's question about showing provisional results to people who will not read these notes,
   and it names a publisher in public, which is Karoline's decision as much as Craig's.
   ANSWERED 2026-09-21 (Karoline), the two questions that were hers:
   **Build shape:** a one-folder build in a zip rather than `--onefile`. Her words: "zip sounds fine".
   So the antivirus worst case is avoided and the download is still a single file.
   **Timing: not yet, and not even for testing.** Her words: "it's even too early for testing purposes
   I'd say. I didn't even yet look at the tool here on Mac Tahoe." So no Windows build and no signing
   now.
   DEFERRED 2026-09-21 (Karoline) on that timing, so that the comparison above would not have to be
   made twice whenever it was taken up.
   SETTLED 2026-09-28 (Karoline), and every step this item proposed was adopted rather than merely
   allowed. The unsigned one-folder zip is now built AND started on a Windows machine by
   `.github/workflows/ci.yml` on every push, so each change proves the program still runs, and
   `.github/workflows/release.yml` builds it on a version tag and attaches it to the GitHub release
   (#83). Karoline chose Windows only for 0.1.0. `RELEASING.md` records the order in the same sequence
   argued above: the SignPath Foundation once a release exists to be signed, the Microsoft Store later
   if the method settles enough to list, and in its own words "a commercial certificate is never bought:
   it would not remove the warning". The correction in (a) to (d) stands exactly as written; what has
   changed is that it is no longer a proposal awaiting a ruling. Her separate remark from 09-21, that
   the tool had not yet been run by the person who asked for it, bears on item 6 rather than here.
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
   SETTLED 2026-09-27 (Karoline, choosing among her agent's options): arcs with the same source and target
   merge, across conditions, studies and evidence; the merged strength is the median of their log2 means,
   with the range; arcs whose signs disagree are not merged ("No merge on conflict": only agreeing arcs
   merge); merging is an advanced setting, off by default, with a minimum-supporting-studies filter. Her
   earlier words on #47: "could be condensed into an arc with a number-of-studies-supporting-the-arc
   attribute". Consequences stated by her agent: absent arcs have no direction and stay separate; obligate
   and abolished arcs join their direction and count without entering the median; a merged arc carries no
   sd, se or combined test, lists every study, experiment and condition, and is drop-out evidence if any
   of its arcs is. Edges gain `merged_arcs` and `strength_range` (optional, backward compatible).

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
   SINCE THEN (2026-09-21, Karoline, revising this item): there is no neutral edge. A clean comparison whose
   spread crosses zero keeps the sign of its mean and gets `status` absent (item 15, threshold k); obligate
   and abolished edges take their direction from the outcome and are always present.
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
   AMENDED 2026-09-21 (Karoline, on #62): "change the default treatment for the single_replicate case and
   ... show those edges but take care in the cytoscape style that they are marked somehow, e.g. dashed."
   They keep the flag and an undetermined `status`; the other low-quality flags stay hidden by default.
   SINCE THEN (2026-09-21, item 15): absences are exported as edges with `status` absent and hidden by the
   display, so only one display setting remains, "Show low-quality edges", off by default.

22. **Conditions recorded only in descriptions** (Karoline, 2026-09-27). A co-culture was compared with
   the monocultures that share its recorded conditions (cultivation mode and every compartment field:
   medium, temperature, pH, volume, stirring, gases, pressure, dilution rate, inoculum), and a drop-out
   with the full community under the same conditions. But mGrowthDB records supplements, concentrations,
   starting densities and lineages only in the free-text description, so monocultures grown differently
   were pooled: SMGDB00000013 pooled evolved and ancestral lines, SMGDB00000014 0% to 1% oleic and
   linoleic acid, SMGDB00000015 glutamate and starting densities from about 10^2 to 10^7, SMGDB00000007
   the controls of three experiments. Karoline's decision, her words: "yes to 1-3, and 4 is noted", for
   these proposals of her agent:
   1. monocultures are pooled only when their descriptions also agree (apart from a run number), as
      communities already are;
   2. when several monoculture sets fit a co-culture, the one whose description names that co-culture
      experiment is used (SMGDB00000007: 'controls of the "bhri" experiment'); otherwise the pair is
      skipped with the reason and the candidates, never guessed;
   3. edges from co-cultures of a pair that differ only in their description (SMGDB00000004's +Ac and
      -Ac), and drop-out arcs whose full community or drop-out has such variants, carry the caution
      `conditions_unverified`: shown, and marked;
   4. the lasting fix is in mGrowthDB: supplements, concentrations, starting density and lineage as
      recorded fields (noted by Karoline for mGrowthDB).
   Then, for SMGDB00000013, whose names pair up ("Evolved AtCt" with "Evolved At", "CtOa" with the plain
   "Ct"), a qualifier rule, used only when no description names the co-culture: the monoculture set whose
   name carries the same words before its last one. Karoline: "yes". A pair matched by name or qualifier
   carries no `conditions_unverified`, since the names account for the variants.
   Effect: SMGDB00000004 keeps its 20 edges, 16 cautioned; SMGDB00000007 compares each co-culture with
   its own controls; SMGDB00000008 is unchanged; SMGDB00000013 gives 9 edges, each compared with its own
   line (Ochrobactrum to Comamonas is now obligate: the plain Comamonas monoculture did not grow, where
   the pooled set of plain, ancestral and evolved lines did); SMGDB00000014 derives nothing, its 15
   monoculture variants per strain differing in concentrations no name or description ties to a
   co-culture.

23. **One species-identifying technique on both sides** (Karoline, 2026-09-27). Her words: "mono-cultures
   should only be compared to co-cultures if both use the same, species-identifying technique, even if
   another technique would result in the same unit, because otherwise we do not know whether an effect is
   due to the co-culture or due to the change in technique." So a species' curves in the sets compared
   (monocultures and co-cultures, or a full community and a drop-out) must share mGrowthDB's
   `techniqueType`, beyond the unit check; different species may be measured differently. Whole-culture
   measurements (subject bioreplicate: OD, pH, total counts) are not species-identifying and are not used
   for monocultures either, as before (SMGDB00000010 and SMGDB00000015 measure their monocultures only that
   way). No edge derived from mGrowthDB on 2026-09-27 changed: every one already compared one technique.

24. **Merging to genus, and a genus as a query** (Karoline, 2026-09-28). Her words: "another advanced option
   that is by default deactivated and which returns the network with nodes merged at the genus level and
   arcs merged by strain/species (depending on the query). Arc merge needs to be stratified by sign and a
   new arc attribute should record the number of strains/species supporting an arc. Please note that this
   option may be used together with the option to merge arcs across studies." Choosing among her agent's
   options: the count is of distinct pairs "at entry level" (species pairs, or strain pairs when every
   entry is an NCBI taxon id, since a name, even with a strain designation, resolves to its whole
   species); interactions within one genus are kept "as a self-loop"; absent arcs: "record them as before
   but do not display them" (one absent arc per genus pair, hidden like any absent arc); and a genus
   entered alone resolves to every strain of it in mGrowthDB ("Yes"). Consequences stated by her agent:
   the genus merge runs after the merge across studies, so with both on a pair measured in several studies
   counts once; the strength is the median, as in item 14; the genus is the first word of the name
   mGrowthDB records ([Clostridium] is not Clostridium), not NCBI's lineage, so a reclassified genus follows
   its names. Edges gain `supporting_pairs` and `merged_pairs`, nodes the identity `genus` (optional,
   backward compatible). After Craig's agent's review of #85 (qualifiers such as "unclassified" made a
   genus of their own), Karoline chose: an organism named like "unclassified Bacteroides" is merged into
   its genus ("Merge into its genus"; mGrowthDB holds none today), and "[Clostridium] scindens" is its own
   genus, [Clostridium], apart from Clostridium ("Its own genus"), as the genus query already treated it.

25. **All of mGrowthDB** (Karoline, 2026-09-28). Her words: "a button next to 'Example' that says: 'All'.
   If this button is pushed, the input field is ignored and instead, the entire interaction network is
   fetched from mGrowthDB (there can be a short explainer next to the button)." Every study the species
   list is read from is derived, with every partner kept; Only these studies and Exclude these studies
   still apply. `derive --live --all` does the same from the command line.

26. **The time window of a bi-culture arc** (open; found by the audit of 2026-09-28). Curves are compared
   over the window they share, so none is extrapolated. For a drop-out arc that window is the target's own
   curves with and without the removed member ("so one short curve elsewhere in the design does not
   shorten it"). For a bi-culture it is every curve of the design, including the source alone, whose
   curve is not part of the comparison. Example, SMGDB00000006: Lactobacillus delbrueckii subsp.
   bulgaricus -> Streptococcus thermophilus STpos compares S. thermophilus over 0 to 6 h, because L.
   bulgaricus alone was followed for 6 h, while both S. thermophilus sets run to 7 h or longer (+0.088 over
   6 h, +0.074 over 7 h; absent either way). The arc's `experiments` does not list the source's
   monoculture that set the window. Options: (a) keep the design-wide window (both arcs of a pair then
   cover the same time); (b) give each bi-culture arc its own window, the target's curves only, as for
   drop-outs, and list nothing more; (c) keep it and add the source's monoculture to `experiments`.
   Proposed by her agent: (b), for consistency with drop-outs and because it uses all the target's data.
   SETTLED 2026-09-28 (Karoline): "Concerning different windows for growth in mono- vs bi-culture (or
   drop-out vs full community): OK." So (b): each arc is compared over the target's own curves in the
   two sets, and "AUC requires an equal time window", which it has: both sets are cut to the same end.

27. **Stationary phase, with max as the measure** (Karoline, 2026-09-28). Her words: "max is problematic
   when the growth curve hasn't reached stationary phase yet (especially if it did in the other case). We
   should test for it (simple & quick) and add a warning on the arc in case stationary phase was reached
   in one case but not the other." And on the first proposal, a flat end: "Roseburia is known to have 2
   growth peaks in some cases. none of the cases above deal with diauxic shift. Please think about a method
   that is not invalidated by diauxic shift. We'll have to pay in run time to avoid this, it's common, and
   we do want to make sure that we are not comparing curves where one reached stat phase and the other
   didn't". Adopted, choosing among her agent's options: a curve reached stationary phase by the window's
   end when (1) over the last fifth of the window it rises by less than 10% of its rise (window maximum
   minus start; a decline counts), and (2) wherever it was measured after the window it never exceeds its
   window maximum by more than 10% of that rise, so a diauxic pause with a measured second rise is not
   stationary; a set follows the "Majority of replicates"; a curve needs "At least 6" points in the window
   to be judged; the warning is for "Max only". Arcs gain the cautions `stationary_phase_differs` and
   `stationary_unchecked` ("A caution of its own"). Tried on mGrowthDB first: on the dense curves
   (studies 2, 4, 6, 7, 13; 7 to 18 points) it calls Roseburia's peaks and second peak stationary and
   flags the B. hydrogenotrophica monocultures still rising at 48 h in study 4; study 8, with 3 or 4 noisy
   qPCR points per curve, is too sparse to judge. A second phase after the last measurement cannot be seen
   by any rule.

28. **Audit 2: what the skip list showed** (Karoline, 2026-09-28, choosing among her agent's options after
   every skip reason over all of mGrowthDB was checked against the data):
   - Matching monocultures (extends item 22): "Match identical wording". When several monoculture sets
     remain after the "named" and "qualifier" rules, the one whose description words the growth like the
     co-culture's, once the organisms and the kind of culture are taken out (the text after "monoculture"
     or "co-culture"), is used, if it is the only one. SMGDB00000014's five At+Ct co-cultures (0.1% and
     0.75% linoleic acid, ROS, TBHQ, DMSO) each match their own monocultures this way: 10 arcs.
   - A set that is zero from its first time point: "Obligate, with a caution". SMGDB00000006's STneg
     monoculture reads 0 throughout, so L. bulgaricus -> S. thermophilus LMG 18311 stays obligate and gains
     the caution `zero_at_start`: no growth cannot be told from no inoculum or counts below detection.
   - A curve starting after the design's common start: "Only for its own arcs". Its replicate is left out
     of that member's arcs and still serves the others (with the per-arc windows of item 26). In
     SMGDB00000008, 24 of the 26 arcs of two drop-outs regain their second replicate.
   - The report: "One line per experiment" for the average bioreplicates mGrowthDB marks, which were a
     quarter of the skip list; nothing changes in the networks.

29. **Where the Baranyi fit stops** (Karoline, 2026-09-28, after the settings audit). Fitted to whole
   curves, the Baranyi-Roberts model was rejected on 152 curves of mGrowthDB that decline after their peak
   or grow in two phases, so studies 7 and 13 gave no Baranyi arcs. She chose "Fit up to the maximum", and
   then, when her agent showed that cutting at the first maximum leaves early-peaking curves too few points
   (34 arcs), "End of the plateau": the fit uses the curve up to its maximum and on along the plateau after
   it, while the log abundance stays within 10% of the rise below the maximum (the tolerance of item 27),
   and stops at the first point below that. On mGrowthDB: 30 -> 40 Baranyi arcs (easylinear gives 49);
   study 2 recovered, study 7 up from 0 to 10. Easylinear, the default, is unchanged. This helps curves
   that decline after their peak only: a curve with two growth phases has its maximum in the second, so
   nothing is cut and the model still refuses it (Craig's agent, reviewing #88). Values moved too: of the
   29 arcs present before and after, 23 changed strength and 8 sign or status, most on Roseburia targets,
   whose declining curves had inflated the fitted rate.

30. **The All network, derived once a day** (Karoline, 2026-09-28; open for Craig on #96). Her words, on
   scaling: "For the All network, could we build it, save it in grownet's github, serve from there if
   less than a day old", and "There's no mGrowthDB dev for the moment, so let's serve the All network
   from the grownet repository." Built as her agent proposed on #96: a daily workflow publishes All with
   the default settings as a release asset (not in git), and All reads it when it is less than a day old
   and the settings are the defaults. Craig's agreement is asked on publishing a derived network, on the
   daily Actions run and on the one-day freshness. SETTLED 2026-09-28 (Craig, through his agent on #96):
   "Yes to all three: publish, daily, and a network up to 24 hours old." On whether mGrowthDB's terms
   allow publishing derived networks, Karoline (2026-09-29): "the All network also comes with a report
   which lists all studies concerned, so it can be credited. The report will be stored alongside the
   network for fetching." The workflow publishes `all_report.txt` next to the network; its sources list
   cites every study behind an arc, with its title and DOI.

31. **Filtering on the adjusted p-value** (Karoline, 2026-09-30). Found by comparing grownet with an
   earlier analysis of three studies (a local audit): that analysis called an interaction only when its
   adjusted p-value was below 0.05, grownet by the absence threshold alone, so grownet reported more. Her
   words: "we leave p-value computation and correction as is, it just needs to be better documented.
   Then, please add an advanced option, by default off, that allows filtering arcs on adjusted p-value.
   the help should motivate why the filter on adjusted p-value is off by default". So the test (Welch's
   t-test on the per-replicate log2 values), the correction (Benjamini-Hochberg, or Benjamini-Yekutieli)
   and its family (every comparison of one derivation, rather than per study, which her agent had
   suggested) stay as they were. Choosing among her agent's options: the threshold is "Settable, 0.05
   default" (`--max-adjusted-p Q`); an interaction above it is "Left out, counted"
   (`meta.hidden.not_significant`); arcs without a p-value (obligate, abolished, a single replicate):
   "Keep them, labeled untested" (the caution `untested`). The filter runs after the adjustment and
   before merging. Why it is off by default, as the help says: with two or three replicates per side
   the test misses many real effects, and an adjusted p-value depends on the other comparisons in the
   same search.

32. **The adjacency matrix, the reported growth rates and the gLV parameters** (Karoline, 2026-10-03).
   Her words: "The next job is supporting another network export format: the adjacency matrix. In
   addition, grownet should be able to provide parameters for generalized Lotka-Volterra (gLV) simulation
   tools ... building an adjacency matrix with negative (-1) entries on the diagonal in which each strain
   (or species or genus) only appears once (so merge across studies) and where the same is true for the
   growth rates that are delivered together with the interaction matrix. Both should be package such that
   they can easily be parsed to gLV simulators." Her three choices, from the options her agent put to her:
   a cell holds the "log2 mean as-is", the effect size the comparison measured, not a rescaled or fitted
   coefficient; a reported growth rate is the "Maximum specific growth rate in monoculture (easylinear, as
   mGrowthDB reports), median across replicates and studies, with the per-study values kept beside it";
   the package is a "Zip of two CSVs + README". The conventions her agent set and recorded on #108, none
   contradicted: an empty cell is 0 and so is an arc below the absence threshold, since the threshold
   judged it no interaction; rows are affected and columns are the actor, so `A[i][j]` is the effect of j
   on i, the order dx_i/dt = x_i (r_i + sum_j A[i][j] x_j) reads in; arcs of one ordered pair merge by
   their median (item 14), and a pair whose arcs disagree in sign is left at 0 and named in the README,
   since a simulator should not be handed a number no one stands behind. AMENDED the same day, after her
   agent reported that an obligate or abolished arc would then sit at 0 like an empty cell although it is
   the strongest interaction there is: "obligate and abolished arcs need to carry numbers reflecting the
   strong effect, how about 10 with the appropriate sign?" So obligate is +10 and abolished -10
   (`matrix.EXTREME`), a stated extreme rather than a measurement (as a log2 mean it is a thousandfold
   difference), named cell by cell in the package README. Following item 14, such an arc does not enter
   the median of the arcs that do have a ratio: it sets a cell only when no arc of that pair was
   quantified, and a pair whose extreme contradicts a measured arc is a sign conflict like any other. The -1 diagonal is a convention
   for self-limitation, not a normalization of the rest, and the README says a cell is an effect size, not
   a fitted gLV coefficient (a per-capita effect in absolute units). Rates come from batch monocultures
   only: in a continuous culture the rate a curve shows is the dilution rate (item 12), and a rate measured
   in a co-culture is growth with a partner, which is the comparison itself.

Once a default lands as a `Deriver`, the FP/BH slice reruns against it unchanged, so settling these does
not cost rework.
