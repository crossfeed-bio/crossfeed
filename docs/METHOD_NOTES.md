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

## What the provisional baseline does today

So the note matches the code rather than an intention. `src/crossfeed/derive.py` (`BaselineDeriver`) is a
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

1. Growth metric: **growthRate (1/h)**, paired with a comparison that suits a rate (see 1 and 3 together)
2. Per-strain signal in a community: **per-strain qPCR, as the study reports it**
3. Mono versus co comparison: **log2(co / mono) with a deadband**, coupled to the metric in 1
4. Significance and uncertainty: **qualitative point estimate now**, replicate-based once it is wired
5. Co-culture scope: **pairwise, two member**
6. Technique mismatch: **flag on every edge**, and do not trust the sign near the band under a mismatch
7. Taxonomic identity: **genus and species today**, plus an NCBI taxid on every node (needs building)
8. Environment and medium: **keep all conditions, tag each edge**; restriction waits on mGrowthDB metadata
9. Drop-out (leave one out) communities: **exclude from the default network**
10. Edge thresholds: **minimum strength 0, minimum supporting studies 1**, meaningful once edges merge
11. Minimum time points: **carry the fit quality mGrowthDB reports**, gate on it rather than a fixed count
12. Chemostats and serial dilutions: **flag and keep separate from batch**
13. Output format: **JSON canonical, GraphML on demand**

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

## The decisions that actually matter

Most rows have an uncontroversial default. The ones worth real discussion, in rough order:

- **Settings 1 and 3**, the metric and comparison as a coupled pair (rate with a log ratio is unstable).
- **Setting 7**, an NCBI taxid on every node and the merge rank, which is what makes the microbetag and
  Syntropa overlay actually compose rather than duplicate nodes.
- **Setting 4**, wiring replicate uncertainty through, then which significance test.
- **Setting 6**, how far to trust a mismatched-technique sign, and whether to restrict or calibrate.
- **Setting 10**, merging edges per interaction before a replication floor can mean anything.

Once a default lands as a `Deriver`, the FP/BH slice reruns against it unchanged, so settling these does
not cost rework.
