# What grownet does not know

This file lists the questions grownet cannot settle from the data it reads, what it publishes instead of a
number that would imply they were settled, and what would settle each one. It exists because those
questions kept reading as blockers while they are properly caveats: none of them stops a network or a gLV
package from being derived, and every one of them changes how a reader should take a number.

The rule behind it, which the rest of the tool already follows: **where the data cannot settle a question,
publish the measurement and name the weakness.** A censored cell of the adjacency matrix holds `NA` with
the bound on the arc rather than a number that cannot say it is a floor; a carrying capacity ships with
how far its curves fell from their peak; an arc ships the share of the course its rows cover; a gLV
package states what the model assumes rather than implying the assumptions hold. Those are not apologies,
they are the output.

Two things this file is not. It is not a list of defects: a defect gets fixed, and anything here is a
property of the designs mGrowthDB holds. And it is not a license to change what a published number means:
withholding a number or documenting a weakness costs nothing, while redefining a field's meaning moves the
format id (see the format contract in [AGENTS.md](../AGENTS.md)).

Each entry: **what is not known**, **what is published instead**, **what would settle it**, **what it
blocks**. The settled method decisions, with their reasoning, are in [METHOD_NOTES.md](METHOD_NOTES.md).

---

## 1. Whether a monoculture rate is the rate that organism had in co-culture

**Not known.** The default derivation fits each organism's row by holding its monoculture growth rate
fixed and fitting the partners' coefficients around it. The arc is then the only free parameter left to
absorb any difference between that rate and the rate the organism actually had in the co-culture, so a few
per cent of such a difference can publish a significant arc that is not there. **No growth curve in a
monoculture-versus-co-culture design measures it**: the co-culture is a condition the monocultures were
never grown in.

**Published instead.** `rate_mismatch_to_zero` on every arc: the fractional error in the held rate that
would move this arc's coefficient to zero, exactly, since the fit is affine in that rate. An arc needing
0.5 survives a 50 per cent error; one needing 0.04 does not. Where a study matched the organism to more
than one monoculture set, the spread of the rates those sets fitted enters `se` as a third component
(`se_rate_selection`, with `rate_selection_spread`), which is measured but is a **lower bound** on the gap,
since it compares two monoculture conditions rather than a monoculture with a co-culture. An arc whose
organism has one matched set in its study carries the `rate_unchecked` caution: nothing there checks the
assumption, which is not the same as checking it and passing. The report prints the mismatch beside the
q-value for the same reason.

**What would settle it.** A design that measures each organism's growth rate inside the co-culture, which
mGrowthDB's per-strain series can give where both members are counted over time. That is a derivation, not
a correction, and it is out of scope for 0.3.0.

**Blocks.** Nothing. It bounds how a p-value should be read, which is why the p-value decides nothing.

## 2. Whether a fitted growth rate is biologically plausible

**Not known.** Nothing in the derivation compares a growth rate with anything outside its own fit. The
guards are identifiability, model fit, growth above zero and the fit against the interaction-free null; a
rate's **magnitude** is never questioned. Of 123 monoculture fits that pass every guard, three imply a
doubling slower than 24 hours and all three are from one study of fast aquatic organisms.

**Published instead.** The doubling time the rate implies, `ln(2) / r`, in `growth_rates.csv` and beside
every rate in the report. It catches nothing automatically; it converts a number nobody rejects at a
glance into one they do, which is the only cheap half of this question.

**What would settle it.** Either a cited per-taxon bound, which is a scientific statement about those
organisms and needs a source rather than a judgement, or a tripwire that compares a study's fits against
the corpus, since the implausibility is concentrated in one study rather than scattered. The second needs
no citation and is the better first move; it waits until something published rests on such fits.

**Blocks.** Nothing today: that study derives no arcs, so no matrix cell rests on those fits. The rate
still publishes in the rates table, which is why the doubling time is printed there.

## 3. What the absence threshold means inside a matrix

**Not known.** An arc below the absence threshold is reported as no interaction, which is a statement
about evidence. A matrix cell of zero is a statement about the model: that organism has no effect on this
one. The two are not the same claim, and the threshold was chosen for the first.

**Published instead.** The threshold and its k travel with every network (`meta.absence`), the matrix
package names the cells it left at zero for disagreeing in sign, and `effect_over_sd` is published per arc
so a reader can apply another k without rederiving.

**What would settle it.** A decision about what a zero cell asserts, which is a modeling choice rather
than a measurement. It is open on #124 with the background Karoline asked for.

**Blocks.** Nothing. It changes what a zero in the matrix should be read as.

## 4. Which abundance a partner's coefficient should be divided by

**Not known.** A per-capita coefficient needs one partner abundance, and a batch co-culture gives a curve.
The mean over the window the rate estimator fitted is what the package uses; the maximum, the value at the
window's end and the mean over the whole course are all defensible and give different numbers.

**Published instead.** The choice is stated in the package README and in the help page, the partner's
abundance travels on every arc (`partner_abundance`, with its unit and the number of replicates behind
it), and nothing is converted between abundance units: a search spanning several writes one matrix per
unit rather than one matrix with invented conversions.

**What would settle it.** Agreement on what `x_j_star` is, or a reader-supplied unit bridge, both open on
#124.

**Blocks.** Nothing. It is a stated convention whose inputs are published, so a reader can recompute a
cell under another choice.

## 5. When a culture has reached stationary phase

**Not known.** `reached_stationary` certifies a plateau over a curve's last fifth, which accepts a culture
that grew, peaked and then declined, and records its peak as the plateau. Reading the condition at the end
of the curve instead would refuse those curves and lose their capacities.

**Published instead.** The carrying capacity ships with `capacity_fall`, the median factor by which those
curves fell from their peak, and with how many curves gave no capacity and why. A reader can see a
declining culture rather than discovering it.

**What would settle it.** A decision about which definition the plateau should take, with the capacities
it would gain or lose measured first. Open in METHOD_NOTES.

**Blocks.** Nothing. It changes which curves certify a capacity.

## 6. Whether the gLV model describes these communities at all

**Not known, and partly known to be false.** A gLV model assumes pairwise interactions that add up and
coefficients that do not change with the environment. In a batch culture the medium changes as the culture
grows, and with it the interactions: a pair that competes for a resource while it is plentiful can
cross-feed on what is left once it is gone. A higher-order interaction, where a third organism changes how
two others affect each other, has no term in this model and cannot be fitted into one.

**Published instead.** The package README and the help page state both assumptions in full, every arc
reports the share of the measured course its rows cover (`fit_window_share`, with the `window_partial`
caution below a half), and each coefficient's medium travels with it, since a simulation is of one
environment.

**What would settle it.** Nothing within batch growth data. Designs that hold the environment fixed, such
as the chemostats mGrowthDB holds, test the parameters rather than the assumption; a community series with
more than two members would let a higher-order term be fitted, which is a different model.

**Blocks.** Nothing. It is the standing caveat on every number in a gLV package.

---

Each entry above is a live issue or a settled decision with its measurements: #155 item 1, #173, #124
(items 1, 6 and 7), the `reached_stationary` decision in METHOD_NOTES, and the model assumptions the gLV
package states. The numbers quoted here were measured on mGrowthDB as it stood on 2026-10-08 and move with
it; the report beside any download says what was read and when.
