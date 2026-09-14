# Derivation method: choices to make together

mGrowthDB serves growth curves, not interactions. Turning growth into a directed, condition-specific
interaction is a scientific choice, and it belongs to the collaboration (K. Faust, H. Zafeiropoulos), not
to this code. This note lays out the choices as a menu so we can pick together. It is not a decision.

The provisional baseline (`src/crossfeed/derive.py`, `BaselineDeriver`) picks the simplest option in each
row below, only so the seam runs end to end on real data today. Each pick is a placeholder. Any choice
replaces the baseline by implementing a new `Deriver` (see [CONTRIBUTING.md](../CONTRIBUTING.md)); nothing
else in the pipeline changes.

## 1. The growth metric

What number stands for "how well a strain grew"?

- **growthRate (1/h)** [baseline]: a rate, so it travels reasonably across measurement techniques.
- **AUC**: total growth over the run; sensitive to the density technique and the time window.
- **maximum OD or carrying capacity**: the plateau; misses dynamics.
- **lag time or yield**: captures a different axis of the interaction.

## 2. Reading a per-strain signal inside a community

A co-culture measures the community; an interaction needs each strain's own growth.

- **per-strain qPCR** [baseline]: direct per-strain counts, when the study reports them.
- **deconvolution from community OD**: model each strain's share; assumptions matter.
- **relative abundance from sequencing**: when amplicon or shotgun data accompany the growth data.

## 3. Comparing mono against co, and defining the effect

- **log2(co / mono) with a deadband** [baseline]: symmetric, unitless; the deadband sets neutral.
- **difference or normalized effect size**: an alternative scale that some tests prefer.
- The **direction** (facilitation, inhibition, neutral) follows from the sign; the **threshold** is a choice.

## 4. The significance test

- **none, qualitative** [baseline]: every edge is marked qualitative; no p-value is claimed.
- **a replicate-based test** (for example a t-test or Mann-Whitney across bioreplicates): needs
  replicate-level values, not just the summarized rate.
- **an effect-size threshold**, optionally with **multiple-testing correction** (FDR) across all pairs.

## 5. Scope of the co-cultures

- **pairwise, two-member only** [baseline]: a clean attribution of who affected whom.
- **larger communities**: possible, but needs a rule for attributing a per-strain change to a specific
  partner rather than to the whole community.

Several real mGrowthDB studies are built on larger communities. Study SMGDB00000007 is mostly pairwise
and works with the baseline today; study SMGDB00000008 is a species-deletion design with 13 to 14 member
consortia, so the pairwise baseline skips all of it and the network comes back empty. Supporting that
class of study (deletion or leave-one-out designs, and community subsets) is one of the higher-value
method choices to make.

## 6. The technique-mismatch caveat

In the FP/BH demonstration study the monoculture growth is measured by flow cytometry or optical density
while the per-strain co-culture growth is measured by qPCR. The baseline records this on every edge and
flags a mismatch, so the direction is dependable while the magnitude is provisional. The options are to
flag it (baseline), to calibrate between techniques, or to restrict a network to matched techniques.

## The first question for the FP/BH slice

Which option in rows 1 to 4 should the first real network fix, and do we want it to carry a significance
call from the start or stay qualitative until we agree on the test? Once that is settled, it lands as a
`Deriver` and the slice reruns against it unchanged.
