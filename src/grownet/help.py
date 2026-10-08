"""The help page of the local page (#78): settings, arc attributes, decisions, the command line, Q&A.

The content is data, keyed by the names the code uses, so the tests can require an entry for every
advanced setting (`gui.DEFAULTS`), every command line option of `derive`, and every node and edge field of
the model. Adding any of those without a line here fails the tests, the same way the legend works.
"""
from __future__ import annotations

import html

from . import __version__, rbridge
from .brand import COMMAND, NAME
from .idea import idea_figure

REPOSITORY = "https://github.com/crossfeed-bio/crossfeed"
R_INSTALL = rbridge.INSTALL_R
R_TROUBLE = rbridge.INSTALL_TROUBLE
ISSUES = f"{REPOSITORY}/issues"
NEW_ISSUE = f"{ISSUES}/new/choose"
MGROWTHDB = "https://mgrowthdb.gbiomed.kuleuven.be"
# the local page's download of the Cytoscape style; the token is filled in when the page is written
STYLE_LINK = "/grownet_style.xml?token=__TOKEN__"

# The About page (#80): the wording Craig agreed to on #80, naming both builders; change it only with
# their agreement.
ABOUT = (f"{NAME} was built by Karoline Faust (KU Leuven) and Craig Heilmann (Syntropa), working through "
         "their AI coding agents (Claude).")

# What changed in each release, a few lines each, newest first (Karoline, 2026-10-04: "a small log of what
# happened in each new release"). The changelog in the repository is the full record; this is the summary a
# user of the page wants, so each line says what they can now do rather than what moved in the code. A test
# requires the newest entry to be this version, so a release cannot forget it.
RELEASES = (
    ("0.3.0", "2026-10-06", (
        "The gLV parameters are fitted coefficients, not effect sizes: the diagonal is -r_i / K_i from "
        "each organism's own plateau, and an off-diagonal cell is whatever its derivation fitted, which "
        "the package states. Every cell is a per-capita effect in 1/(time x abundance), so nothing in "
        "the package is a convention and nothing needs scaling.",
        "One matrix per abundance unit, since a conversion between cells, colony-forming units and grams "
        "would have to be invented. The page says before the download when a package will hold more "
        "than one.",
        "A pair where one side did not grow is a measurement too, not a stated extreme: its coefficient "
        "comes from the rate that was measured and the one that was 0. In the plain adjacency matrix such "
        "a cell now holds NA instead of +/-10, and the measured bound the no-growth rule gives it travels "
        "on the arc, which can say it is a bound where a cell cannot.",
        "A growth rate now travels with the lag the Baranyi fit found, the estimator that produced it "
        "and the organism's carrying capacity, which are the three numbers a coefficient is made of.",
        "Every growth rate is printed with the doubling time it implies, in the rates file and in the "
        "report. No stage of the derivation asks whether a rate is plausible, and 47 hours is rejected "
        "at a glance where 0.0147 per hour is not.",
        "A package can be scored against the chemostat steady states mGrowthDB holds for the same "
        "organisms, which were never used to fit it: predicted against observed, per organism.",
        "A gLV example button beside All: it fills both boxes and the settings for a package that "
        "settles, and runs the search. The help walks that package through miaSim step by step, and "
        "ends by holding the simulated steady state against the co-culture it was fitted from.",
        "The default derivation fits each organism's whole row from the measured time course instead of "
        "comparing replicate sets, which needs no growth property and gives the coefficients directly. "
        "The comparison of replicate sets is Derivation in Advanced settings, or --derivation replicate, "
        "and is unchanged.",
        "Send to R and the R package carry the same numbers as the download, and the package reads the "
        "parameters of 0.2.0 as well, telling the two apart.",
    )),
    ("0.2.0", "2026-10-04", (
        "Export a network as an adjacency matrix, and as the parameters a generalized Lotka-Volterra "
        "simulation takes: the interaction matrix, the growth rates beside it and a README of what the "
        "numbers are and are not.",
        "Send those parameters straight into R, with the companion package in the repository's r folder; "
        "it hands them to miaSim or to your own code, and it carries their caveats with them.",
        "A second box beside the species says where to look: a medium, an experiment or a study. Every arc "
        "now records the medium it was measured in.",
        "The gLV mode switch sets what a simulation needs: growth rates on, drop-out communities off.",
        "significance is now -log10 of the q-value, so larger means stronger evidence, and the q-value has "
        "its own column. A network said it speaks grownet.interaction_network/v1 because of it.",
        "Arcs below the absence threshold are left out of the downloads and of Cytoscape, so the page, the "
        "files and Cytoscape all count the same interactions.",
    )),
    ("0.1.0", "2026-09-29", (
        "The first release: the local page, the command line, networks as JSON or GraphML, Send to "
        "Cytoscape with the legend's style, and the report that says how every arc was derived.",
    )),
)

# key in gui.DEFAULTS -> (label on the page, command line flag, what it does and when to change it)
SETTINGS = {
    "derivation": ("Derivation", "--derivation integrated|replicate",
                   "How an interaction is derived. integrated (the default) fits each organism's whole "
                   "row from the time course, ln(x_i(T) / x_i(0)) = r_i T + sum_j A_ij integral(x_j dt), "
                   "over its growth phase, so it needs no growth property and no abundance of its own to "
                   "divide by, and it gives the gLV coefficients directly. It is the default because it "
                   "is the form published work fits for this purpose and because the alternative's "
                   "coefficient carries the organism's own density as a confound. Each arc carries the "
                   "spread of its coefficient over the co-culture replicates and over leaving out each "
                   "monoculture replicate, how much of the organism's log abundance change the fit "
                   "explains, and the condition number of the design; a row that explains less than "
                   "predicting nothing does is refused and named, as is a row the design cannot "
                   "identify, and a community of three or more is reported rather than derived, since an "
                   "arc fitted inside one would be a new kind of evidence. It needs a time course: a "
                   "study measured at two or three points gives it nothing. replicate is the comparison "
                   "the collaboration specified, a growth property of the replicates with the partner "
                   "against the replicates without it, and it needs only two measurements per set, so "
                   "it is what a sparsely sampled study can still give."),
    "metric": ("Growth property", "--metric auc|max|growth_rate",
               "The growth property compared with and without the partner. The area under the curve (auc, "
               "the default) combines lag, rate and yield in one number; the maximal abundance (max) keeps "
               "yield only; growth_rate is the maximum specific growth rate, set by the two settings below."),
    "rate_method": ("Growth rate method", "--rate-method easylinear|baranyi",
                    "Used with growth_rate. easylinear (the default) fits straight lines to log abundance over "
                    "sliding windows and takes the steepest part, as mGrowthDB computes the rates it reports "
                    "(it matched them on 190 of 192 curves within 10%). baranyi fits the Baranyi-Roberts growth "
                    "model to the curve up to the end of the plateau after its maximum, so a decline after the peak "
                    "does not matter; a curve "
                    "it still does not describe (for example two growth phases) is left out and reported, never "
                    "given another number."),
    "rate_window": ("Growth rate window", "--rate-window N",
                    "Used with easylinear: how many consecutive points each fitted line spans. 5, the default, "
                    "is what mGrowthDB uses; fewer points follow noise, more flatten the steepest part."),
    "include_low_quality": ("Show low-quality edges", "--include-low-quality",
                            "Low-quality edges carry a quality flag (pooled strains, a continuous culture "
                            "compared on a measure that does not suit it, a "
                            "drop-out whose removed member was still detected). They are computed but not "
                            "shown by default, and never read as an absence of interaction. Single-replicate "
                            "edges are always shown, flagged."),
    "include_absent": ("Include arcs below the absence threshold", "--include-absent",
                       "Off by default, so a downloaded file and a network sent to Cytoscape hold exactly "
                       "the interactions this page counts: one number everywhere. The arcs the threshold "
                       "marked absent are reported in their own section of the result and in the report, "
                       "with how many there were. Tick it to keep them in the file as well, with status "
                       "absent: each carries effect_over_sd, the quantity k cuts, so you can move the "
                       "threshold in Cytoscape on that column without searching again."),
    "include_dropout": ("Include drop-out communities", "--no-dropout",
                        "Arcs from a community compared with the same community without one member. On by "
                        "default; --no-dropout leaves them out. Such an arc says the removed member affects "
                        "the target, directly or through other members, so it is labeled evidence dropout, "
                        "and the gLV mode button unticks it: a gLV coefficient is meant to be the direct "
                        "effect of one organism on another, which an arc that may act through a third "
                        "species is not. It applies to the comparison of replicate sets only: the default "
                        "derivation refuses a community of three or more members, since fitting a row "
                        "inside one is a new kind of evidence and needs a decision first, so with it this "
                        "setting changes nothing either way and the report says so."),
    "include_non_batch": ("Include chemostat and serial dilution experiments", "--include-non-batch",
                          "What a continuous culture can be compared on depends on the growth measure. With "
                          "max it is derived without this setting: the level such a culture settles at is "
                          "comparable with and without a partner, and those arcs are shown with the caution "
                          "continuous_culture. With auc or a growth rate it is left out, because the area "
                          "under a diluted run says how long it ran and its growth rate is the dilution "
                          "rate; this setting derives it anyway, and then the edges carry the non_batch "
                          "flag and are hidden with the other low-quality ones. A comparison never mixes "
                          "modes: a chemostat co-culture is compared only with chemostat monocultures."),
    "absence_threshold": ("Absence threshold k", "--absence-threshold K",
                          "Decides when an interaction counts as absent, that is, when the data show the "
                          "species do not affect each other: its effect is small against its own spread, "
                          "|log2 mean| < k times the standard deviation. The default 1 means the mean plus "
                          "or minus its sd crosses zero. Raise k for a stricter network, where fewer "
                          "interactions count as present; 0 marks only a mean of exactly zero absent. Absent "
                          "interactions stay in the downloads with status absent."),
    "correction": ("Multiple testing correction", "--correction bh|by",
                   "How the p-values of the test the derivation ran are adjusted for multiple testing, over every "
                   "comparison one search tests (every arc of every study it reads, absent and low-quality "
                   "ones included): Benjamini-Hochberg (default) or the more conservative "
                   "Benjamini-Yekutieli, which holds under any dependence between tests. The adjusted "
                   "p-value is the q-value, the number the result table heads q. It supports an "
                   "interaction and decides nothing, unless the filter below is on (see How an interaction "
                   "is decided, above)."),
    "max_adjusted_p": ("Filter on the q-value", "--max-adjusted-p Q",
                       "The q-value is the p-value adjusted for multiple testing: the two names mean the "
                       "same number, and the result table heads that column q. "
                       "Off by default. When ticked, an interaction whose q-value is above the "
                       "threshold (0.05 unless you type another) is left out as well, and the page and the "
                       "file count how many. Absent and undetermined arcs are not interactions and stay as "
                       "they are; an arc without a p-value (obligate, abolished, a single replicate) is kept "
                       "and marked untested; merging uses only the arcs that passed. It is off by default for "
                       "two reasons: with two or three replicates per side, as in most of mGrowthDB, the test "
                       "misses many real effects, and a q-value depends on the other comparisons "
                       "in the same search, so the same arc can pass in one search and fail in another. "
                       "Turn it on for a network whose false discovery rate is controlled, at the cost of "
                       "missing effects (see How an interaction is decided, above)."),
    "spike_factor": ("Spike limit", "--spike-factor F",
                     "A replicate curve with one or two interior points more than F times above both "
                     "neighbors (default 100) is left out and reported, with the other measurements of the "
                     "same replicate named. 0 keeps every curve."),
    "capacity_max_fall": ("Carrying capacity decline limit", "--capacity-max-fall F",
                         "A monoculture that grew, reached a peak and then declined has stopped growing, "
                         "so it is certified as having reached stationary phase, and the carrying "
                         "capacity recorded for it is that peak. A curve whose last measurement is below "
                         "1/F of its peak (default 10) gives no capacity and is named with the others "
                         "that gave none, because there the peak is a spike rather than a level the "
                         "culture held. A decline is the ordinary shape of a batch culture, so this is a "
                         "limit on how far, not a refusal of decline: 0 keeps every certified plateau."),
    "no_growth_alpha": ("No-growth alpha", "--no-growth-alpha ALPHA",
                        "Before any comparison, grownet checks that a species grew. It takes the replicate "
                        "growth curves of that species in one culture condition (alone, or with its "
                        "partner) and tests their rise, log2(maximum / first time point) per replicate, "
                        "with a paired t-test; each curve's maximum is taken at whatever time that curve "
                        "peaks. Curves that rose neither significantly at this level nor by the factor "
                        "below did not grow, which makes an interaction obligate or abolished. 0 switches "
                        "the check off."),
    "no_growth_factor": ("No-growth factor", "--no-growth-factor F",
                         "The rise that counts as growth whatever the test says: the geometric mean, over "
                         "the replicate growth curves, of maximum / first time point. 1.5 is a medium "
                         "default; 2 (one doubling) is more stringent. 0 leaves the test alone."),
    "merge_arcs": ("Merge parallel arcs", "--merge-arcs",
                   "Off by default, since interactions are condition-specific. On, the arcs from one strain to "
                   "another, across conditions, studies and evidence, become one arc: its strength is the median "
                   "of their log2 means, with the range, and it lists every study, experiment and condition it "
                   "rests on. Arcs whose signs disagree are not merged; absent arcs stay separate."),
    "merge_genera": ("Merge to genus", "--merge-genera",
                     "Off by default. On, every strain becomes its genus, and the arcs between two genera merge "
                     "by sign, so two genera can be joined by a facilitation arc and an inhibition arc. The "
                     "strength is the median of the merged arcs' log2 means, with the range, and "
                     "supporting_pairs counts the distinct species pairs behind the arc, or strain pairs when "
                     "only NCBI taxon ids were entered. Interactions within one genus stay, as an arc from the "
                     "genus to itself; absent arcs become one absent arc per genus pair, hidden as before. With "
                     "Merge parallel arcs on as well, the arcs of each pair are merged across studies first, so "
                     "a pair measured in several studies counts once. The genus is the first word of the name "
                     "mGrowthDB records, not NCBI's lineage, so a reclassified genus follows its names."),
    "min_studies": ("Minimum supporting studies", "--min-studies N",
                    "Keeps arcs resting on at least this many studies. Above 1 it needs merged arcs, since an "
                    "arc as derived rests on one study."),
    "conditions": ("Media, experiments or studies", "--conditions NAME [NAME ...]",
                   "This one is the second box beside the species, not an advanced setting, because it says "
                   "where to look rather than how to decide an interaction. Empty by default, which looks "
                   "at every medium. A medium is matched as text, case-insensitively, against the medium "
                   "name mGrowthDB records on the experiment's compartments, its description and its name, "
                   "so \"wilkins\" finds every spelling of Wilkins-Chalgren and \"mucin\" finds the "
                   "experiments that mention it; an id picks one study (SMGDB...) or one experiment "
                   "(EMGDB...), and naming a comparison keeps the monocultures it is made against. One "
                   "word can reach several media: a medium with a sugar added or a carbon source left out "
                   "is another environment, and SMGDB00000026 varies the sugars in Wilkins-Chalgren "
                   "seventeen ways. Those are never pooled, they give separate arcs, and the report names "
                   "every medium a search read, so name an experiment id to read one of them alone. On the "
                   "command line a study id given this way replaces the study argument."),
    "exclude_studies": ("Exclude these studies", "--exclude-studies IDS",
                        "Comma separated mGrowthDB study ids that are never searched, for example a study "
                        "you know to be unsuitable. Empty by default. It applies after the second box, "
                        "so a study named in both is left out."),
    "only_entered": ("Only interactions between the species entered", "--all-partners",
                     "On by default: an edge is kept when both ends are species you typed. Untick it, or give "
                     "--all-partners, to see every partner of your species in the studies found."),
    "steady_check": ("Check against chemostat steady states", "--steady-check",
                     "Off by default. With it on, and with Report growth rates, the gLV parameters are "
                     "scored against the steady states mGrowthDB holds for these organisms in continuous "
                     "culture: a chemostat satisfies A x = -(r - D) at steady state, and those numbers "
                     "were never used to fit the parameters, so they test them. The comparison is in the "
                     "report and in the package, with every chemostat it could not use and why. It reads "
                     "the curves of those chemostats, which a search does not otherwise need."),
    "report_rates": ("Report growth rates", "--report-rates",
                     "Off by default, since a rate costs a fit per curve. With it on, every organism in the "
                     "network also gets its maximum specific growth rate in monoculture, the median over the "
                     "replicates and studies that have one, downloadable as its own CSV and used by the gLV "
                     "parameters. Batch monocultures only: in a chemostat the rate a curve shows is the "
                     "dilution rate. The gLV mode button turns it on."),
}

# command line options of `derive` that are not advanced settings -> what they do
CLI_ONLY = {
    "--glv-mode": "the page's gLV mode button, from the command line: --report-rates, --no-dropout and "
                  "--metric growth_rate together, which is what a fitted coefficient needs",
    "--rates": "write the growth rates to a CSV file, the page's Download the growth rates (needs "
               "--report-rates)",
    "--glv": "write the parameters of a generalized Lotka-Volterra simulation to a zip file, the page's "
             "gLV parameters, Download (needs --report-rates)",
    "--steady-check": "score those parameters against the chemostat steady states mGrowthDB holds for "
                      "these organisms, since a continuous culture satisfies A x = -(r - D) at steady "
                      "state and was never used to fit them: the report gets the comparison and the zip "
                      "a steady_state_check.txt (needs --report-rates and --live)",
    "--to-r": "send those parameters into an R session waiting for them, the page's gLV parameters, Send "
              "to R (needs --report-rates; the companion package's grownet_listen() is what waits there)",
    "--r-port": "the port that R session listens on (default 8793, what grownet_listen() uses)",
    "--species": "species, strain or genus names, or NCBI taxon ids: search every study holding them, as the page "
                 "does",
    "--all": "every study in mGrowthDB, with every partner, as the page's All button (with --live)",
    "--no-published": "with --all, derive live instead of reading the network derived once a day",
    "--live": "fetch from the mGrowthDB API (the normal case)",
    "--fixture": "derive from a JSON list of interaction records instead (offline, for testing)",
    "--deriver": "plug in your own derivation method, given as module:ClassName (one study at a time)",
    "--format": "json (the neutral format, default) or graphml (Cytoscape, igraph, networkx, Gephi)",
    "--out": "write the network to a file instead of the screen",
    "--report": "write the report of the search to a file, as the page's Report button downloads it",
    "--to-cytoscape": "also send the network into a running Cytoscape on this machine, with the legend's style",
    "--cytoscape-port": "the port Cytoscape's CyREST listens on (default 1234)",
}

# Edge field -> meaning. The GraphML attribute has the same name.
EDGE_ATTRIBUTES = {
    "source": "the organism whose presence is varied (node id)",
    "target": "the organism whose growth is measured (node id)",
    "effect": "facilitation (the target grows more with the source) or inhibition (less); neutral for a mean "
              "of exactly zero, which has no direction",
    "strength": "log2 of the target's growth with the source over without it, as the mean over replicates; "
                "empty for obligate and abolished",
    "sd": "standard deviation of the strength, the spread of the comparison",
    "se": "standard error of the strength",
    "n_with": "replicates with the source present",
    "n_without": "replicates with the source absent",
    "weight": "|strength|, always positive, for widths and layouts",
    "effect_over_sd": "|strength| / sd, the number the absence threshold cuts; filter on it to apply "
                      "another k",
    "status": "present, absent (below the absence threshold), or empty when undetermined (a single "
              "replicate or a low-quality edge)",
    "p_value": "the unadjusted p-value of the test the derivation ran, which the network's "
               "meta.statistics names: Welch's two-sided t-test on the per-replicate log2 values for the "
               "specified comparison of replicate sets. It is SUPPORT and it decides nothing: the status "
               "comes from the absence threshold, and the q-value filter is off unless you set it. Read "
               "it with what it rests on, which is two or three replicates, and with what it assumes: "
               "for the integrated form the null holds the monoculture rate as the rate the organism had "
               "in co-culture, which no growth curve in these designs measures, so rate_mismatch_to_zero "
               "beside it says how large a mismatch would explain the arc away and rate_unchecked marks "
               "an arc with nothing in its study to check that against",
    "q_value": "that p-value corrected for multiple testing over every comparison of the search, the q "
               "on the page (see How an interaction is decided). Support, like the p-value it comes from",
    "significance": "-log10 of the q-value: larger is stronger evidence against the test's own null, 0 at "
                    "q = 1, and a style can map it continuously. It is capped at 15 for a q-value of "
                    "zero. It is a restatement of the q-value and inherits what that rests on",
    "outcome": "quantified (a ratio was computed), obligate (the target grows only with the source), "
               "abolished (only without it), or no_growth",
    "metric": "the growth property compared: auc, max, or a growth rate with its rule "
              "(growth_rate:easylinear:5, growth_rate:baranyi)",
    "method": "how the edge was computed, in words",
    "quality": "flags that make the edge low quality: single_replicate, strains_pooled, non_batch, "
               "removed_member_detected; empty means no issue found",
    "cautions": "remarks that do not lower quality: two_replicates (exactly two replicates on a side), "
                "conditions_unverified (experiments of this pair differ only in their description, such as a "
                "supplement, and nothing recorded says which monocultures or drop-outs match which), "
                "stationary_phase_differs (with max as the measure: one set reached stationary phase and the "
                "other did not, so its maximum may still be rising), stationary_unchecked (with max: too few "
                "time points, under 6, to tell), zero_at_start (an obligate or abolished arc whose set without "
                "growth is zero from its first time point, so no growth cannot be told from no inoculum or "
                "counts below detection), continuous_culture (a chemostat or serial dilution arc, compared "
                "on max: the level a culture settles at is comparable with and without a partner, while an "
                "area under the curve or a growth rate of such a run is not), untested (with the adjusted "
                "p-value filter on: the arc has no p-value, so the filter kept it without judging it), "
                "window_partial (the fitted rows cover less than half the measured course, because the "
                "integrated model has no lag term and no death term and stops at the end of the plateau "
                "after the maximum: the effect one organism has on another can change along the growth "
                "curve, and the coefficient describes the phase inside the window), rate_unchecked (an "
                "arc of the integrated form whose organism has one matched monoculture set in its study, "
                "so nothing there measures how much its fitted rate moves when the matched condition "
                "moves: se and the p-value carry the replicates and the monoculture stage, and the one "
                "assumption this design cannot test, that the monoculture rate is the rate the organism "
                "had in co-culture, is unchecked rather than checked. rate_mismatch_to_zero says how "
                "large a mismatch would explain the arc away)",
    "notes": "other remarks, for example a replicate left out for a spike, the span of the course the "
             "rows cover, or what each side of the comparison was inoculated at, measured from the first "
             "time point because mGrowthDB's inoculum field is empty and its descriptions are not "
             "systematic. A starting density is reported and never matched on: the two sides of a "
             "comparison are not meant to begin at the same density, so refusing a comparison for that "
             "would discard measurements rather than confounds",
    "evidence": "biculture (monoculture against a two-member co-culture: a direct interaction) or dropout "
                "(a community against the same community without the source: direct or indirect)",
    "community": "the members of the culture the arc comes from: the pair for a co-culture, the full "
                 "community for a drop-out arc",
    "condition": "the experiment the edge comes from; interactions are condition-specific",
    "cultivation_mode": "batch, chemostat, and so on, as mGrowthDB records it",
    "medium": "the growth medium the comparison ran in, as mGrowthDB names it on the experiment's "
              "compartments; empty when it names none",
    "partner_abundance": "the source's own abundance in the co-cultures, averaged over the window the "
                         "target's growth rate was fitted in; the x_j a gLV coefficient divides by",
    "partner_abundance_unit": "the abundance unit that number is in, as measured; never converted",
    "partner_abundance_n": "co-culture replicates behind that median",
    "metric_with": "the target's own growth property in the co-culture, as a number rather than a ratio: "
                   "the geometric mean over the replicates with the source present, which is what a "
                   "fitted coefficient is built from",
    "metric_without": "the same without the source; 0 means the target did not grow at all there, which "
                      "is what an obligate outcome records",
    "target_capacity": "the target's own plateau in the co-culture, where its curves reached stationary "
                       "phase: what fits the self-limitation of an organism that grows only with a partner",
    "target_capacity_unit": "the abundance unit that plateau is in, as measured; never converted",
    "target_capacity_n": "co-culture replicates behind that plateau",
    "strength_bound": "for a comparison where one side did not grow, the measured bound the cell holds "
                      "instead of a ratio: at least this much facilitation, or at most this much "
                      "inhibition, from the no-growth rule's own numbers",
    "bound_rule": "what that bound rests on, in words: the factor the rule allows and the measured start "
                  "it applies to",
    "coefficient": "with a derivation that fits the row rather than comparing sets: the gLV coefficient "
                   "it fitted, a per-capita effect in 1/(time x abundance)",
    "coefficient_unit": "the unit of that coefficient",
    "fit_r2": "how much of the organism's own log abundance change that fit explains, about zero, since "
               "the model has no intercept, and over the replicates the fit actually used",
    "fit_null_r2": "the same for the same row with every partner's effect set to zero: the line a fitted "
                   "row has to beat to be a measurement of an interaction rather than of the organism's "
                   "own growth, and the difference is how much the partners bought",
    "fit_window_share": "the share of the measured course the fitted rows cover. The integrated model "
                        "has no lag term and no death term, so the rows start where growth starts and "
                        "stop at the end of the plateau after the maximum; a course measured well past "
                        "its peak is fitted on the early part of itself. Below half, the arc carries the "
                        "window_partial caution. grownet fits one constant coefficient per arc, so an "
                        "effect that changes along the growth curve, competition first and facilitation "
                        "later, is reported as whatever it was inside the window",
    "rate_mismatch_to_zero": "the fractional change in the fitted monoculture growth rate that would "
                             "drive this arc's coefficient to zero, exactly, signed: positive means the "
                             "rate would have to be that much higher. The monoculture rate is held fixed "
                             "when the partners are fitted, so the arc is the only parameter left to "
                             "absorb a difference between the rate the organism had on its own and the "
                             "rate it had beside its partner, and nothing in a growth curve can measure "
                             "that difference. Read it as how much of that difference this arc needs to "
                             "be explained away: an arc at 0.5 survives a 50 per cent error in the rate, "
                             "an arc at 0.04 does not survive 4 per cent",
    "coefficient_sd": "the spread of the fitted coefficient over the co-culture replicates: one "
                      "coefficient per replicate, at the rate stage's own estimate. The monoculture "
                      "stage's contribution is a separate number beside it, measured on its own design, "
                      "so the two are never mixed",
    "coefficient_n": "the co-culture replicates behind that spread, which is a count of cultures",
    "coefficient_sd_from_rate_stage": "the part of the coefficient's uncertainty that comes from the "
                                      "monoculture stage, on its own design: that stage is resampled "
                                      "over its monoculture replicates and the coefficient recomputed at "
                                      "each resample, which it can be exactly, since it is an affine "
                                      "function of the rate and the self-limitation",
    "se_replicates": "the part of se that comes from the co-culture replicates: their spread over the "
                     "square root of their number. With a derivation that fits the row, sd is the "
                     "dispersion of one estimate including the monoculture stage, so that the tool's own "
                     "relation se = sd / sqrt(n) holds and the absence threshold carries that stage too; "
                     "the replicates' own scatter is this number times the square root of n",
    "se_rate_stage": "the part of se that comes from the monoculture stage, from resampling it. se is "
                     "the square root of the variances added, and the p-value is a t statistic on "
                     "it with a Satterthwaite degrees of freedom, so an arc whose monoculture stage is "
                     "poorly determined is not tested as though that stage were exact",
    "se_rate_selection": "the part of se that comes from which monoculture set the condition matcher "
                         "gave stage 1. Where a study holds several sets for one organism, its arcs can "
                         "be matched to different ones, and the rates those sets fit differ; this is "
                         "what that spread moves the mean strength by. Empty where the organism has one "
                         "selected rate in the study, which is most arcs. It is a lower bound on what "
                         "the arc assumes, since the gap it stands for is between a monoculture and a "
                         "co-culture the monocultures were never grown in",
    "rate_selection_spread": "the spread of those selected rates, in the rate's own units, which is the "
                             "measured scale behind se_rate_selection. The arc's notes name the rates "
                             "and say how far apart they are",
    "rate_stage_method": "how the monoculture stage was resampled for that number: a bootstrap of its "
                         "replicates where the stage is the median of one fit per replicate, or a "
                         "delete-one jackknife where it is one regression over all of their rows",
    "rate_stage_n": "the monoculture replicates that resampling rests on",
    "fit_condition": "how well the fit was determined: the condition number of the normal equations of "
                     "its design, every column scaled, so a large number means the columns were too "
                     "close to tell apart. It is the square of the design's own condition number, and "
                     "it is the largest over the fit's stages",
    "experiments": "the mGrowthDB experiments whose replicates the edge compares",
    "study_ids": "the studies supporting this edge; cite them (see Sources)",
    "merged_arcs": "with Merge parallel arcs: how many arcs of this source and target were merged into this one; "
                   "empty for an arc as derived",
    "strength_range": "with Merge parallel arcs: the lowest and highest log2 mean of the merged arcs; the "
                      "strength is their median",
    "supporting_pairs": "with Merge to genus: how many distinct species pairs (strain pairs when only taxon ids "
                        "were entered) this genus arc rests on",
    "merged_pairs": "with Merge to genus: those pairs, as source -> target",
}

# Node field -> meaning
NODE_ATTRIBUTES = {
    "id": "ncbi:<taxon id> for a strain with an NCBI taxon id, otherwise genus and species from the name",
    "name": "the strain name, as the study records it",
    "taxon_id": "the NCBI taxon id of the strain, as mGrowthDB records it",
    "species": "genus and species from the name, to merge with species-level networks",
    "identity": "what the id rests on: ncbi (the taxon id), name, or genus (with Merge to genus: the node "
                "stands for every strain of its genus)",
    "taxonomy": "a lineage, when known",
    "model_ref": "a link to a metabolic model, when known",
}

# (decision, why), with the issue that settled it
DECISIONS = (
    ("Interactions are derived, not looked up.",
     "mGrowthDB stores growth curves. grownet compares each species' growth with and without a partner "
     "across replicates, on your machine, each time you search (#34)."),
    ("One number per comparison: the mean log2 ratio of the replicate sets.",
     "log2(with) minus log2(without) per species, averaged over replicates, with the spread of both sets "
     "combined in the sd. A log ratio is symmetric: a doubling is +1 and a halving is -1 (#3)."),
    ("Curves are compared over the time they share.",
     "Areas and maxima are taken from the common first time point to the earliest last time point of the "
     "curves compared (for a bi-culture, every curve of the design; for a drop-out arc, the target's curves "
     "with and without the removed member), interpolating at that end, so no curve is extrapolated (#1)."),
    ("An edge is present by its size against its spread, not by a p-value.",
     "With two or three replicates a real effect rarely reaches significance, so the test is reported as "
     "support and does not decide. The absence threshold k does: |mean| of at least k sd (#40, #54)."),
    ("A measured absence is kept, as status absent.",
     "\"We looked and found nothing\" is a result, so absent edges stay in the downloads and are hidden "
     "from view, not deleted (#54)."),
    ("Low quality is not absence.",
     "An edge with a quality flag keeps the sign of its mean and is hidden by default; it is never called "
     "absent, because a weak measurement says nothing about whether the interaction exists (#40)."),
    ("Growth is checked before any ratio.",
     "With two or three replicates a real rise rarely reaches significance, so a set counts as grown when "
     "the paired test finds a rise or when it rose by the factor (1.5 by default). The strong claims, "
     "obligate and abolished, then need two reasons rather than one underpowered test (#37, #68)."),
    ("No growth is a result.",
     "A target that grows only with its partner is obligate; one that grows only without it is abolished. "
     "Both are the extremes of their direction and are always shown (#16)."),
    ("Nodes are strains, keyed by NCBI taxon id.",
     "Names change: taxon 411483 is Faecalibacterium prausnitzii A2-165 in one study and Faecalibacterium "
     "duncaniae A2-165 in others, after the 2022 reclassification. Names are resolved through mGrowthDB "
     "only, which keeps one source of truth (#23, #24)."),
    ("Drop-out communities count, labeled as possibly indirect.",
     "A community without one member shows what that member does, but maybe through the others (#47)."),
    ("A species is compared only with itself measured the same way.",
     "Its monocultures and co-cultures must use the same species-identifying technique, not only the same "
     "unit, since otherwise an effect could be the change of technique; whole-culture measurements such as "
     "OD are not used for this."),
    ("Experiments are pooled only when they are replicates.",
     "Interactions depend on the environment, so experiments with different conditions give parallel "
     "arcs, one each (#47)."),
    ("A culture is compared on a measure its mode supports.",
     "Chemostat and serial dilution runs are derived with max, the level they settle at, and left out with "
     "an area under the curve or a growth rate, which measure something else under dilution (#42, amended "
     "2026-10-03)."),
    ("Suspect curves are flagged, never silently dropped or replaced.",
     "A replicate with an implausible spike is left out and reported, with the other techniques measured "
     "on it named (#39)."),
    ("Merging summarizes; it is off by default.",
     "Interactions are condition-specific, so arcs are shown as derived. Merge parallel arcs and Merge to "
     "genus condense them on request: by the median, never across signs, and with Merge to genus each arc "
     "says how many species pairs it rests on. Merged across studies first, a pair measured in several "
     "studies counts once (register items 14 and 24)."),
    ("The genus comes from mGrowthDB's names.",
     "It is the first word of the name mGrowthDB records, after qualifiers such as Candidatus or "
     "unclassified, and not NCBI's lineage. NCBI's brackets stay: [Clostridium] scindens is placed outside "
     "Clostridium, so its genus is [Clostridium]. A reclassified genus follows its names: Phocaeicola "
     "(former Bacteroides) is its own genus."),
    ("grownet never corrects source data.",
     "Errors in mGrowthDB records are fixed in mGrowthDB, so every user sees the same data."),
    ("Everything runs on your machine.",
     "The page is served from 127.0.0.1 with a token, has no JavaScript, and the tool needs nothing beyond "
     "Python's standard library."),
)

# (question, answer as HTML)
QA = (
    ("A name is not recognized.",
     "Under Not used, each entry says why: unreadable, a taxon id no strain in mGrowthDB carries, a genus "
     "without its species, or a name mGrowthDB does not hold, with the names it does hold that you may have "
     "meant. Names are resolved through mGrowthDB's own strain records, so also try the other name of a "
     "renamed species (Faecalibacterium prausnitzii or duncaniae), the strain name, or the NCBI taxon id. "
     "Several names on one line, separated by commas, and ids written as txid476272 work too."),
    ("A GraphML file opened in Cytoscape does not look like the legend.",
     "A file carries no style. Send to Cytoscape applies it; for a downloaded file, "
     f"<a href=\"{STYLE_LINK}\">download the grownet style</a> (or write it with "
     f"<code>{COMMAND} style --out grownet_style.xml</code>), import it in Cytoscape (File, Import, Styles "
     "from File) and choose grownet in the Style panel. The file holds every column the style maps (the "
     "line style, the width and the genus color)."),
    ("Gephi shows fewer arcs than the network has.",
     "A pair can have several arcs (one per condition or study). Gephi may merge parallel edges of one pair "
     "when it imports a file; the GraphML keeps every arc, and each carries its condition and study. Use "
     "Merge parallel arcs or Merge to genus to condense them on purpose, or read the arcs in the JSON."),
    ("The search is slow.",
     "Every study holding your species is fetched live from mGrowthDB. Name the studies you need in the "
     "second box, beside the species: a study id there (SMGDB...) reads that study and no other."),
    ("\"mGrowthDB is not reachable\" or \"search failed\".",
     "The machine cannot reach mGrowthDB. Check the internet connection, or open "
     f"<a href=\"{MGROWTHDB}\">mGrowthDB</a> in the browser to see whether it is up, then try again."),
    ("The browser did not open, or a page says \"missing or wrong token\".",
     "Open the address grownet printed in the terminal, including its ?token= part. "
     f"<code>{COMMAND} gui --no-browser</code> only prints it."),
    ("\"cannot use port\".",
     "Another program holds that port. Leave out <code>--port</code> to use a free one, or pick another."),
    ("An edge has no number.",
     "Obligate and abolished edges have no ratio, because one side did not grow. The direction and the "
     "replicate counts are the result."),
    ("Where are the absent edges?",
     "Under \"edge(s) below the absence threshold\" on the result page, and in both downloads with status "
     "absent."),
    ("An edge looks wrong.",
     "Check its replicate counts, flags and notes, then the curves in mGrowthDB. A problem in the data "
     "belongs to mGrowthDB; a problem in the tool belongs in the issue tracker (below)."),
    ("Today's network differs from an earlier one.",
     "mGrowthDB gains and corrects data. Every network and report records the tool version, when it was "
     "derived, and each study's upload and publication dates, so two files can be told apart and a "
     "corrected study shows up as a new date."),
    ("How do I open the network in Cytoscape?",
     "Start Cytoscape, then press Send to Cytoscape under the result: the network arrives with the legend's "
     "style. Without the button, download GraphML and choose File, Import, Network from File in Cytoscape, "
     f"then give it the style: <a href=\"{STYLE_LINK}\">download the grownet style</a> and import it with "
     "File, Import, Styles from File."),
    ("Can Gephi or another tool read the network?",
     "Yes: download GraphML and open it in Gephi (File, Open), igraph or networkx. Nodes carry their strain "
     "name as label, and edges their weight (|log2 mean|) and every attribute listed above."),
    ("\"could not reach Cytoscape\".",
     "Cytoscape is not running, or its CyREST port is not 1234. Start Cytoscape and wait until it has "
     "opened, then press the button again."),
    ("How do I stop grownet?",
     "Press Ctrl+C in the terminal where it runs."),
)

EXAMPLE_CLI = (f'{COMMAND} derive --live --species "Faecalibacterium duncaniae" "Blautia hydrogenotrophica" '
               '--out example.json --report example_report.txt --to-cytoscape')


def _e(x) -> str:
    return html.escape(str(x), quote=True)


def _name(field: str) -> str:
    """A field name that may break after its underscores, and nowhere else, on a narrow screen."""
    return "<code>" + _e(field).replace("_", "_<wbr>") + "</code>"


def _table(head, rows) -> str:
    th = "".join(f"<th>{_e(h)}</th>" for h in head)
    return f"<table><tr>{th}</tr>" + "".join(rows) + "</table>"


SECTIONS = (("what", "What grownet does"), ("idea", "The idea behind it"), ("measures", "Which growth measure"),
            ("where", "Choosing where to look"),
            ("example", "Try the example"), ("reading", "Reading the result"),
            ("statistics", "How an interaction is decided"),
            ("glv", "The matrix, the growth rates and gLV"),
            ("glv-assumptions", "What a gLV model assumes"),
            ("glv-walkthrough", "The gLV example, step by step"),
            ("settings", "Advanced settings"), ("attributes", "Arc and node attributes"),
            ("decisions", "Why it works this way"), ("cli", "The command line"),
            ("empty", "No network came back"), ("qa", "Questions and problems"), ("cite", "How to cite"),
            ("issues", "Report a problem or ask for a feature"))


def render_help(token: str, defaults: dict, example: tuple, job: str = "") -> str:
    """The help page body. `defaults` is gui.DEFAULTS and `example` gui.EXAMPLE, passed in to keep this
    module free of the server."""
    t = _e(token)
    legend_job = _e(f"&job={job}") if job else ""      # so the legend's Back returns to the search
    toc = "".join(f"<li><a href=\"#{key}\">{_e(title)}</a></li>" for key, title in SECTIONS)
    # a list, not a four-column table, so it reads at phone width too
    settings = "<dl class=\"settings\">" + "".join(
        f"<dt>{_e(label)}</dt><dd><span class=\"muted\">Command line <code>{_e(flag)}</code>, default "
        f"{_e(_default(defaults[key], key))}</span><br>{_e(text)}</dd>"
        for key, (label, flag, text) in SETTINGS.items()) + "</dl>"
    edges = _table(("Arc attribute", "Meaning"), (
        f"<tr><td>{_name(k)}</td><td>{_e(v)}</td></tr>" for k, v in EDGE_ATTRIBUTES.items()))
    nodes = _table(("Node attribute", "Meaning"), (
        f"<tr><td>{_name(k)}</td><td>{_e(v)}</td></tr>" for k, v in NODE_ATTRIBUTES.items()))
    decisions = "".join(f"<li><strong>{_e(d)}</strong> {_e(why)}</li>" for d, why in DECISIONS)
    qa = "".join(f"<dt>{_e(q)}</dt><dd>{a.replace('__TOKEN__', t)}</dd>" for q, a in QA)
    cli_only = "".join(f"<li><code>{_e(k)}</code>: {_e(v)}</li>" for k, v in CLI_ONLY.items())
    pair = " and ".join(example)
    return f"""<h2 class="page">Help <span class="version">{NAME} {_e(__version__)}</span></h2>
<ol class="toc">{toc}</ol>

<h2 id="what">What grownet does</h2>
<p>Type species names, one per line, strain names, a genus (it stands for every species of it in
mGrowthDB), or NCBI taxon ids. grownet looks them up in mGrowthDB, reads the growth curves of every study
that holds them, and derives the interactions between them on this machine. The All button ignores the
box and derives every study in mGrowthDB, with every partner. With the default settings, All reads the
network the grownet repository derives from mGrowthDB once a day, when it is less than a day old, which
spares mGrowthDB about 1,300 requests; the result says when it was derived. Any other setting, or GitHub
out of reach, derives it live. Nothing is uploaded, and nothing is written outside the file you
download.</p>

<h2 id="where">Choosing where to look</h2>
<p>The second box beside the species is optional and says <strong>where</strong> to look, not how to decide
an interaction. Leave it empty and every medium is used, which is what grownet did before. One entry per
line:</p>
<ul>
<li>a <strong>medium</strong>, matched as text and case-insensitively against the medium name mGrowthDB
records on an experiment's compartments, its description and its name. The spellings differ between
studies, so a short word finds more: <code>wilkins</code> finds all four spellings of Wilkins-Chalgren,
one of which is misspelled in the database, and <code>mucin</code> finds the experiments that add mucin
beads to the same medium.</li>
<li>an <strong>experiment id</strong> (<code>EMGDB000000024</code>) or a <strong>study id</strong>
(<code>SMGDB00000002</code>). Naming a co-culture or a community also keeps the monocultures it is
compared against, chosen by the usual matching rules, since one id alone would otherwise give no arc; the
report names what came along.</li>
</ul>
<p>Why it matters more than it used to: a network of interactions can carry arcs from several media and
say so on each arc, while a <a href="#glv">gLV simulation</a> takes one matrix of numbers, and numbers from
different environments do not belong in one simulation (Karoline, 2026-10-04). Nothing about the method
changes: a comparison never mixed media, because the medium is part of the conditions two replicate sets
must share. Every arc records its <code>medium</code>, so a network says which environments it came
from.</p>
<p><strong>What counts as one medium.</strong> mGrowthDB names a medium per compartment and does not
report its composition systematically: an added sugar, a removed carbon source or a supplement usually
lives only in the experiment's description ("WC plus mucin beads", "minimal medium with 0.75% linoleic
acid", "RI_BH -Ac"). So a medium's identity is its compartments' names, without case, punctuation or a
parenthesized abbreviation, together with every alteration the description states, with the amount where
one is stated, and the atmosphere where it is recorded. Reading the descriptions tells several times as
many media apart as the names alone do, and the alias table then merges the names that are one medium
spelled two ways. Two media are
the same medium when those agree and not otherwise: a name
that merely contains another is not a match, since "Wilkins-Chalgren Anaerobe Broth (WC)" and
"Wilkins-Chalgren Anaerobe Broth (WC); Mucin" are a one-compartment design and a two-compartment one, and
0.1 and 0.75 percent linoleic acid are two environments. The rule decides what a carrying capacity may be
pooled over, which chemostat a gLV package may be scored against, and what the second box reaches; where
two studies spell one medium differently, grownet says the names differ and names the word rather
than merging names that disagree (Karoline, 2026-10-07).</p>
<p><strong>The alias table.</strong> Two live names disagree with the others rather than being less
complete: SMGDB00000001 writes "Wilkins-Chalgren An<strong>e</strong>robe Broth (WC)", a typo, and
SMGDB00000005 and 26 write "Wilkins-Chalgren" alone, a short form. The rule tells both apart from the
full name, and a looser match would merge names differing by a digit, which in medium names is routine.
So those two are merged by hand, in a table Karoline curates
(<code>grownet.media.WORD_ALIASES</code> and <code>NAME_ALIASES</code>). It is the one place grownet
calls two names that disagree one medium, so it is never silent: a chemostat scored across an alias says
which entry made it one medium, and a carrying capacity whose curves were recorded under more than one
spelling names them all. What a reader sees is always what the study wrote.</p>

<h2 id="idea">The idea behind it</h2>
<p>How one species affects another can be read from growth alone: grow each species by itself, grow the
two together, and compare. Gause showed this with two ciliates feeding on the same bacteria,
<i>Paramecium caudatum</i> and <i>P. aurelia</i> (Gause 1934). Grown separately, each species reached a
stable population. Grown together, both grew at first, then <i>P. caudatum</i> declined until
<i>P. aurelia</i> had displaced it entirely. Set against growth alone, the mixed culture showed how each
species affected the other. grownet makes the same comparison on the growth curves in mGrowthDB.</p>
{idea_figure()}
<p class="muted">An illustration, not data: the curves are drawn with the Baranyi-Roberts model the tool
fits.</p>
<p>A partner that raises a species' growth facilitates it, drawn as a green arc from the partner to the
species; one that lowers it inhibits it, an orange-red arc. The change, as the log2 ratio of growth together
to growth alone over the replicates, is the arc's strength, and a change too small beside its spread
(below the absence threshold) counts as no interaction. Three properties of a curve can be compared,
marked in the figure: the area under the curve (auc, the default), which combines lag, rate and
yield; the maximal abundance (max); and the growth rate, the steepest slope of log abundance (Growth
measure, in the <a href="#settings">advanced settings</a>).</p>
<p>The comparison holds only when both species are counted separately in the co-culture, by a technique
that tells them apart and is the same one used alone, and when alone and together were grown under the same
conditions; grownet checks both (<a href="#decisions">why it works this way</a>). The same comparison runs
on drop-out experiments, a community with and without one member. A change says that the partner affects
the species, not how: cross-feeding, competition for a nutrient, a toxin or a change of pH look the same
here. Gause's yeasts are a case in point (Gause 1932, 1934): in mixed culture without oxygen, a yeast he
named <i>Schizosaccharomyces kephir</i> inhibited <i>Saccharomyces cerevisiae</i> strongly, and only a
separate measurement traced the inhibition to the ethyl alcohol it produced, about twice as much per unit
of yeast volume as <i>S. cerevisiae</i>.</p>
<p class="muted">Gause GF (1932) Experimental studies on the struggle for existence. I. Mixed population of
two species of yeast. Journal of Experimental Biology 9: 389-402.<br>
Gause GF (1934) The Struggle for Existence. Williams and Wilkins, Baltimore.</p>

<h2 id="measures">Which growth measure</h2>
<p>Each measure answers a different question, so an arc can differ between them: on all of mGrowthDB (September 2026)
the area and the maximum agree on the sign of every arc both find, while the area and the growth rate agree on
18 of 23, since a partner can, for example, lower a species' final yield while speeding up its early growth.
Choose it under Growth property in the <a href="#settings">advanced settings</a>.</p>
<dl class="settings">
<dt>Area under the curve (auc, the default)</dt>
<dd>For: it combines lag, rate and yield in one number and uses every point of the curve, so it is robust
to noise in any one of them, and it is defined for any curve with two points. Against: it cannot say which
of lag, rate or yield changed; it needs the same time window on both sides, which grownet ensures; and it
counts the starting abundance too, so a larger inoculum raises it.</dd>
<dt>Maximal abundance (max)</dt>
<dd>For: the simplest to read, the yield a species reaches, unaffected by a decline after the peak, and
the only measure that suits a continuous culture (see below). Against: it rests on one point, so one noisy
measurement moves it, and it ignores timing, so a slow and a fast grower reaching the same level look
alike. It is misleading when one curve reached stationary phase and the other did not; grownet then marks
the arc <code>stationary_phase_differs</code>.</dd>
<dt>Growth rate (growth_rate)</dt>
<dd>For: the speed of growth, independent of yield and of the unit of abundance, and with easylinear the
same method mGrowthDB uses for the rates it reports. Against: it ignores yield and lag; it needs densely
sampled curves (at least 6 points), so a sparsely sampled study gives no rates at all; and it is
sensitive to noise in the steepest part of the curve. easylinear takes the steepest straight stretch of
log abundance and depends on its window; baranyi fits a growth model up to the end of the plateau, and
refuses curves the model does not describe, such as two growth phases.</dd>
</dl>

<h3>Chemostats and serial dilutions</h3>
<p>A continuous culture is diluted while it grows, so what its curve means depends on the measure, and
grownet uses it only where the comparison holds.</p>
<ul>
<li><strong>With max it is derived</strong>, without any setting: such a culture settles at a level, and
that level with a partner against the level without it is the same comparison as in batch. Those arcs are
shown, with the caution <code>continuous_culture</code>, so a reader can tell them from batch arcs.</li>
<li><strong>With the area under the curve or a growth rate it is left out</strong> and reported with its
mode: under dilution the area says mostly how long the run lasted, and the growth rate of a culture held
in steady state is the dilution rate the experimenter chose, not a property of the species. Ticking
"Include chemostat and serial dilution experiments" derives it anyway; those arcs then carry the
<code>non_batch</code> quality flag and are hidden with the other low-quality ones.</li>
<li><strong>A comparison never mixes modes.</strong> The cultivation mode is part of the conditions an
experiment must share to be compared, so a chemostat co-culture is compared only with chemostat
monocultures, never with a batch one.</li>
</ul>
<p>An experiment whose mode mGrowthDB does not record counts as not batch. No study in mGrowthDB holds a
continuous culture that forms a pair or a drop-out design today, so this changes no network yet; it
decides what happens when one arrives.</p>

<h2 id="example">Try the example</h2>
<p>The Example button fills the box with {_e(pair)}, a pair with enough data to show a result: the
<a href="#cli">command line</a> section runs the same search.</p>

<h2 id="reading">Reading the result</h2>
<p>Each row is one directed interaction: a source species, the species it affects, the sign, and the
mean log2 difference with its standard deviation. An interaction counts as present when the effect is at
least k standard deviations of its own spread, with k the absence threshold. The q-value, which is the
p-value adjusted for multiple testing, is shown in the column headed q; it is support and decides nothing,
unless you switch on the filter on it
(<a href="#statistics">How an interaction is decided</a>). Results are provisional: with two or three
replicates, more experiments can change any of them.</p>
<p>While a search runs, a progress bar shows which study is being read, and the page updates by itself.
The result then appears under the settings that produced it, so you can change a setting and search
again. Three buttons sit above the table: <strong>Download network</strong>, with the format (JSON,
GraphML or the adjacency matrix as CSV) in the menu next to it; <strong>Send to Cytoscape</strong>, into a
Cytoscape running on this machine, in the legend's style; and <strong>Report</strong>, which opens the
detailed comments of the search (every setting, every interaction, every pair the data did not support,
the sources) and downloads them as a text file, with the tool version. With <strong>Report growth
rates</strong> on, which is what gLV mode sets, two more outputs appear beside them: the growth rates as
their own CSV, and <strong>Get gLV parameters</strong>
(<a href="#glv">the matrix, the growth rates and gLV</a>).</p>
<p><a href="/legend?token={t}{legend_job}">The legend</a> explains every line, arrowhead and flag.</p>

<h2 id="statistics">How an interaction is decided</h2>
<p><strong>The effect.</strong> For each arc, the target's growth (the chosen measure) is compared between
the replicates with the source and the replicates without it: the log2 of each replicate's value, the mean
on each side, and their difference, the log2 mean. Its standard deviation is its spread over the
replicates.</p>
<p><strong>The call.</strong> An interaction is present when |log2 mean| is at least k standard deviations
(the absence threshold, default 1: the mean plus or minus its sd stays on one side of zero), and absent
otherwise. It is undetermined when one side has a single replicate, since there is then no spread; it is
obligate or abolished when the target did not grow on one side, since there is then no finite ratio.</p>
<p><strong>The p-value.</strong> Every arc with at least two replicates on each side is tested
(<code>p_value</code>). Which test depends on the derivation and the network says so in its
<code>meta.statistics</code>: the comparison of replicate sets runs Welch's two-sided t-test on the
per-replicate log2 values, and the integrated form, which compares no sets, tests its fitted log2
strength against no effect over a standard error carrying both the co-culture replicates and the
monoculture stage. The p-values are adjusted for
multiple testing over every comparison one search tests: every arc of every study the search reads,
absent and low-quality ones included, with Benjamini-Hochberg by default or Benjamini-Yekutieli
(Multiple testing correction). The result is the <strong>adjusted p-value, which is what a q-value is</strong>:
the file calls it <code>q_value</code> and the result table's column is headed q. The two names mean the
same number here, and
<code>significance</code> is -log10 of it, so a larger significance means stronger evidence and a style
can map it continuously (0 at q = 1, capped at 15 when the q-value is zero). Arcs without a test have no
p-value: a single replicate on a side, obligate and abolished arcs,
and merged arcs (Merge parallel arcs, Merge to genus), which are merged after the adjustment and have no
test of their own. The file records the test, the correction and the number of tests in
<code>meta.statistics</code>.</p>
<p><strong>Why the p-value does not decide, by default.</strong> First, with two or three replicates per
side, as in most of mGrowthDB, the test has little power: a large and consistent effect can miss 0.05.
In September 2026, for example, removing Bacteroides ovatus from the SMGDB00000008 community lowered
Lachnoclostridium symbiosum about 29-fold (log2 mean -4.85), with a q-value of 0.052 when the
study was derived alone. Second, an adjusted p-value depends on the other comparisons in the same search:
the same arc gets another value when other studies are read alongside it. Deriving all of mGrowthDB
together, two arcs of SMGDB00000004 passed 0.05 that did not when the study was derived alone, and two of
SMGDB00000007 failed that passed. The absence threshold judges each arc on its own data only.
<strong>Third, for the integrated form the test's null assumes something these designs do not measure.</strong>
That derivation holds the monoculture rate fixed and fits the partners around it, so the null is "no
effect, <em>given</em> that the organism grew at its monoculture rate in the co-culture too". No growth
curve in a monoculture-versus-co-culture design measures whether it did: the co-culture is a condition the
monocultures were never grown in. Two numbers are published beside the p-value for that reason.
<code>rate_mismatch_to_zero</code> says how large a fractional error in that rate would move the arc's
coefficient to zero, so an arc needing 0.5 survives a 50 per cent error and one needing 0.04 does not.
And where the study matched the organism to more than one monoculture set, the spread of the rates those
sets fit is carried in <code>se</code> as a third component (<code>se_rate_selection</code>), which is a
measured but <em>lower</em> bound on the gap, since it compares two monoculture conditions rather than a
monoculture with a co-culture. An arc whose organism has only one matched set in its study carries the
<code>rate_unchecked</code> caution: nothing there checks that assumption, which is different from
checking it and passing. So read a p-value here as support for an effect under a stated assumption, not
as evidence that the assumption holds. The questions grownet cannot settle from these designs are listed
together in <code>docs/LIMITATIONS.md</code>, with what it publishes instead of each.</p>
<p><strong>The filter.</strong> Filter on the q-value, in Advanced settings and off by default,
also leaves out every interaction whose q-value is above a threshold (0.05 unless you type
another). Use it for a network whose false discovery rate is controlled, knowing that it misses effects
the few replicates cannot confirm. The page and the file say how many interactions it left out
(<code>meta.hidden</code>, <code>meta.statistics.filter</code>). Absent and undetermined arcs stay as they
are; arcs without a p-value are kept and marked <code>untested</code>, since the filter cannot judge them;
merging then uses only the arcs that passed.</p>

<h2 id="glv">The matrix, the growth rates and gLV</h2>
<p><strong>The adjacency matrix.</strong> The format menu writes the network as a square table of
comma-separated values, the organisms in the header row and in the first column. A cell holds the log2
mean of the comparison, so <code>A[i][j]</code> is the effect of j on i: rows are affected, columns are
the actor. Each organism appears once, so arcs of one pair from several conditions or studies are merged
by their median, the same rule the Merge arcs setting uses; a pair whose arcs disagree in sign is left at
0 rather than averaged. An empty cell is 0, and so is an arc below the absence threshold, which the
threshold judged no interaction. An obligate interaction (the affected organism grows only with the actor)
has no log2 ratio at all, because one side did not grow, so its cell holds <strong>NA</strong>: neither a
number, which a cell cannot mark as a bound, nor 0, which would read as no interaction about the strongest
effect in the set. The effect is still measured, and it travels on the arc: the no-growth rule allows the
side that did not grow at most its factor (1.5 by default) over its own measured start, which bounds the
ratio from below for an obligate pair and from above for an abolished one. The arc carries that
<strong>measured bound</strong>
(<code>strength_bound</code>) with the rule behind it (<code>bound_rule</code>), the report prints it, and
the page names every cell left NA beside the download. The cell holds NA rather than the bound because a
cell cannot say which kind of number it holds, so a bound printed there is indistinguishable from a ratio,
which is what was wrong with the stated extreme it used to carry. Such an arc sets a cell only when no arc of that
pair was quantified. The diagonal of this matrix is 0; only the gLV package fits it.</p>
<p><strong>A bound on an area is weaker than a bound on a rate</strong>, which matters when the growth
property is the default area under the curve rather than the growth rate gLV mode sets. A culture that
did not grow still carries the area of its own inoculum for the whole window, so the area the rule allows
it can be as large as the area the growing side reached, and the bound then says nothing beyond zero: that
cell stays 0 and the report says so, naming the growth rate and the maximum as the properties that bound
such a comparison tightly. On the maximum the bound is the factor times the measured start, and on a
growth rate it is the rate that would produce the allowed rise over the window, both far under what a
growing side reaches. So a search meant to size an obligate or abolished interaction is better run on the
growth rate or on the maximum, and gLV mode already uses the growth rate.</p>
<p><strong>The growth rates.</strong> With Report growth rates on, every organism in the network also
gets its maximum specific growth rate in monoculture: the method the Growth rate method setting names
(easylinear by default, the one mGrowthDB reports), the median over the replicates and studies that have
one, with each study's own median kept beside it in the network's meta. Batch monocultures only: in a
chemostat or a serial dilution the rate a curve shows is the dilution rate, and a rate from a co-culture
would be growth with a partner, which is the comparison, not the organism's own rate. An organism whose
curves give no rate is named on the page and in the report, never given a substitute number.</p>
<p><strong>Three more quantities travel with a rate</strong>, which is what a gLV coefficient is made of:
which estimator produced the rate; the <strong>lag</strong>, always from the Baranyi fit, the only
estimator that has one, whichever one produced the rate, and empty under the default derivation, whose
model has no lag term at all; and the organism's monoculture
<strong>carrying capacity</strong>, the plateau of its curves, taken only from curves certified to have
reached stationary phase and left in the abundance unit they were measured in. A culture that grew, peaked
and then declined has stopped growing, so it is certified too and its plateau is that peak; how far those
curves had fallen from their peak at the last measurement is published beside the capacity
(<code>capacity_fall_from_peak</code>), which is empty where the capacity is the plateau a fit implies
rather than one a curve reached, since then there is no curve whose fall could be measured; and a curve
that fell further than the
<strong>Carrying capacity decline limit</strong> gives no capacity at all, because there the peak is a
spike rather than a level the culture held. They are in
<code>growth_rates.csv</code>, which names both estimators in its <code>method</code> and
<code>lag_method</code> columns, in the network's meta and in the report, with every curve that gave no
capacity named and why. Each arc also carries <code>partner_abundance</code>, the actor's own abundance in
the co-cultures averaged over the window the target's growth rate was fitted in.</p>
<p><strong>Start with the gLV mode button</strong>, beside All. It sets the three settings a simulation
needs and leaves them in sight in Advanced settings: <strong>Report growth rates</strong> on, since a
simulation needs a rate per organism; <strong>Include drop-out communities</strong> off, since such an
arc compares a community with the same community without one member and the effect may run through a third
species, while a gLV coefficient is meant to be the direct effect of one organism on another; and
<strong>Growth property</strong> on the growth rate, since a coefficient is built from a ratio of rates.
It leaves <strong>Growth rate method</strong> alone, easylinear by default, which is the estimator the
measurements favor; anyone who wants the Baranyi rate sets it there, and the lag is Baranyi's either way.
Name one
medium in the second box as well (<a href="#where">choosing where to look</a>), because a simulation is of
one environment. The package's README says which of these hold for the numbers in it: how many arcs came
from drop-out designs, and which media they were measured in.</p>

<p><strong>The gLV parameters.</strong> The gLV control writes a zip for a generalized Lotka-Volterra
simulator, and since #119 it holds <strong>fitted coefficients</strong> rather than effect sizes:
<code>interaction_matrix.&lt;unit&gt;.csv</code>, one matrix per abundance unit and named after it, where
the diagonal is <code>A[i][i] = -r_i / K_i</code> with K the organism's own monoculture carrying capacity,
and an off-diagonal cell is whatever the derivation fitted, which the package's own README.txt and the
payload's <code>caveats.coefficients</code> state. Under the default, the integrated form, it is a
parameter of the fit of the whole row, <code>ln(x_i(T) / x_i(0)) = r_i T + sum_j A[i][j] integral(x_j
dt)</code>, with the condition number and the residual of that fit on every arc. Under the comparison of
replicate sets it is <code>A[i][j] = (r_with - r_without) / x_j</code>, the difference between i's
own growth rate with j and without it, over the partner's abundance averaged across the window i's rate
was fitted in; both rates come from the same comparison and are in the report, so every cell can be
rebuilt by hand. Where one of them is 0 because i grew only with j, or only without it, the cell is still
that difference: no floor and no stated extreme enters the package, and an organism that grows only with a
partner gets a whole row, <code>r_i = 0</code> with its self-limitation fitted at the plateau it reaches
beside that partner. An organism that does grow alone but whose monocultures never settled is fitted at
its plateau beside its partners in the same way, rather than left out, and the README names it; one whose
partners suppress it harder than its own rate there is named instead, since a self-limitation at or above
zero is not one. The package also carries
<code>growth_rates.csv</code> (one rate per organism, in the same order, with how many values it rests on,
and beside it the estimator, the lag, the carrying capacity and the <strong>doubling time</strong> the rate
implies, <code>ln(2) / r</code> in the time unit of the rate); and <code>README.txt</code>, which states
every formula and unit, names any pair left at 0 for disagreeing in sign, names every organism and every
effect that could not be fitted and why, and names the media the arcs were measured in: a simulation is of
one environment, so a package built from several media says so in capitals and points at the second box
(<a href="#where">choosing where to look</a>). Every cell is a per-capita effect in 1/(time x abundance),
so nothing in the package is a convention and nothing needs scaling to match the rest. Abundances are
never converted between units, which is why each unit has its own matrix: a cell mass conversion would
have to be invented, while the dynamics are the same in any unit. The result section says before the
download when a search spans several units, and how many matrices that means. It is not a loss: organisms
counted differently were never grown together in mGrowthDB, so no effect between them was measured, and
the matrices are separate systems rather than one matrix with corners missing. If you do want them in one
matrix, the factor is yours to apply and to report, as a scaling factor is. A simulation of these numbers can still
grow without bound and come back as NA, which now says something about the measurements, two organisms
fitted as facilitating each other more than each limits itself, rather than about a convention; the
equilibrium of a fit is the solution of A x = -r, and a negative entry there means the fit has no positive
steady state.</p>
<p><strong>The default derivation, from the whole time course.</strong> It fits each organism's row
instead of comparing replicate sets; <strong>Derivation</strong> in Advanced settings (or
<code>--derivation replicate</code>) switches to the comparison of replicate sets, which is unchanged.
Integrating dx_i/dt = x_i (r_i + sum_j A_ij x_j) gives
ln(x_i(T) / x_i(0)) = r_i T + sum_j A_ij integral(x_j dt), which is linear in r_i and in every A_ij, so
one least-squares fit per organism returns its whole row: no growth property, no log2 ratio, no
plateau to certify, and no partner abundance to divide by, since the regressor is the partner's own time
integral. The monocultures identify r_i and its own limitation A_ii, which are then held fixed while the
co-cultures give the partners, because inside one experiment those columns rise too nearly together to
be told apart.</p>
<p>The model has <strong>no lag term and no death term</strong>, so the rows start where growth starts
(the lag the Baranyi fit reports) and stop where it ends (the plateau rule the Baranyi fit uses). Without
those cuts a culture that sits at its inoculum, or declines after its peak, makes the fit pay in the rate,
which showed up as a negative rate on a real study. Every arc carries the coefficient it fitted, the
residual and the condition number of that fit, and a row the design cannot identify is reported rather
than published. A community of three or more members is reported too, not derived: this form could fit a
row inside one, which would be a new kind of evidence and needs a decision first. The growth rates and
the carrying capacities of such a run come from the same fit, the capacity being the plateau it implies,
-r_i / A_ii, so a package is all of one piece.</p>
<p><strong>Scoring the package against a chemostat.</strong> A package is built from batch co-cultures,
and mGrowthDB also holds continuous cultures, where a community sits at a steady state that satisfies
A x = -(r - D) with D the dilution rate. Those numbers were never used to fit the parameters, so they test
them. <strong>Check against chemostat steady states</strong> in Advanced settings (or
<code>--steady-check</code>) puts the comparison in the report and a <code>steady_state_check.txt</code>
in the package: predicted against observed, per organism, with every chemostat it could not use and why
(a run with no dilution rate recorded, a perturbed run, another abundance unit, another medium, or no
organism in common). It is off by default, because it reads the curves of chemostats a search does not
otherwise need. The check's own output names every continuous culture it found and what it did with
each, so which ones qualify is read from the run rather than from this page.</p>
<p>So a package needs the comparison to be on the <strong>growth rate</strong>: the area under the curve
and the maximum cannot produce the ratio L. gLV mode sets that, and without it the page says which
setting to change rather than converting the wrong quantity. The rate estimator sets where a package
settles as well as how fast a simulation runs: the diagonal's r_i is a median over replicates and
studies while each off-diagonal uses its own comparison's two rates, x_j_star is the mean over the
window that estimator fitted in, and the rate guards reject different curves. The equilibrium of a
package, the solution of A x = -r, therefore belongs to the estimator that produced it, and the
package names which one that was.</p>

<p><strong>In R, with the companion package.</strong> The same control sends the parameters straight into
a running R session, which is what the R package in this project is for. It assumes no simulator: it
hands over a plain matrix and a plain vector, with a helper that shapes them for
<a href="https://bioconductor.org/packages/release/bioc/html/miaSim.html">miaSim</a>, whose
<code>simulateGLV</code> solves dx/dt = x(b + Ax), the order this matrix is written in.</p>
<p><strong>This route carries the same numbers as the zip</strong> (the payload is
<code>grownet.glv/v1</code>): fitted coefficients, one matrix per abundance unit, with the rates and what
each one is made of beside them, and every caveat as a field rather than as prose. So nothing there needs
scaling, and <code>glv_scale()</code> warns when it is called on them and says why: their cells are
already in the units of the diagonal they sit beside, and a fit whose cells outweigh the organisms' own
limitations has no bounded state, which scaling hides rather than settles. It stays in the package for the
parameters of 0.2.0 and earlier, which the R package still reads and tells apart.</p>
<pre>install.packages("remotes")
{_e(R_INSTALL)}
library(grownet)
glv &lt;- grownet_listen()        # then press Get gLV parameters, Send to R
glv                            # prints what it holds and what to read before simulating
A &lt;- glv_matrix(glv)           # one matrix per abundance unit: glv_matrix(glv, unit = ) picks one
r &lt;- glv_rates(glv)

args &lt;- as_miasim(glv)         # no scaling: these are coefficients, in 1/(time x abundance)
# miaSim simulates with stochasticity and migration on (stochastic = TRUE, migration_p = 0.01).
# For the deterministic model, call it yourself with stochastic = FALSE and migration_p = 0.
tse &lt;- do.call(miaSim::simulateGLV, c(args, list(x0 = rep(0.1, args$n_species))))

x &lt;- SummarizedExperiment::assay(tse)          # one row per organism, one column per time point
matplot(t(x), type = "l", lty = 1, xlab = "time", ylab = "abundance")
legend("topleft", legend = rownames(x), lty = 1, col = seq_len(nrow(x)), bty = "n")</pre>
<p class="hint">{_e(R_TROUBLE)}</p>
<p><strong>One set per listen, and R says when it arrives.</strong> Every arrival prints the summary
above in the R session, so you can see that a new set came in and which one you are now holding: nothing
is replaced silently. <code>grownet_listen()</code> takes one parameter set and returns it, so run it
again before each send, including after restarting {NAME}, whose new run has its own address and token.
Sending while nothing is listening changes nothing in R; the page says so and shows the line that fetches
the same parameters instead.</p>
<p>The caveats travel as data, not as text to be read first: the object prints them every time,
<code>glv_matrix()</code> warns and names the cells that hold +10 or -10 and takes
<code>placeholders = "na"</code> or <code>"zero"</code> to convert them, and
<code>as_miasim()</code> stops when an organism has no growth rate, since a simulation cannot invent one.
<code>glv_readme()</code> prints grownet's own README, and <code>glv_write()</code> saves the three files
the download holds. When a port cannot be opened, <code>grownet_glv(url)</code> reads the same parameters
from the address the page shows under its gLV control.</p>

<h2 id="glv-assumptions">What a gLV model assumes</h2>
<p>The parameters above are fitted from the curves and say what they rest on, and the model they are
fitted to still makes two assumptions that growth data in batch culture does not satisfy. Neither is a
defect in the fit; both are properties of the generalized Lotka-Volterra form itself, and both matter
when a simulation is
read as a prediction rather than as a summary of what was measured.</p>
<p><strong>Every coefficient is constant in time.</strong> One number stands for the effect of j on i for
the whole run. In a batch culture nothing about the environment is constant: the medium is consumed, the
pH moves, metabolites accumulate, and a pair that competes for a resource while it is plentiful can
cross-feed on what is left once it is gone. The effect one organism has on another can therefore change
in size and in sign along the growth curve, and a single coefficient is the average that best described
the interval that was fitted, not a property of the pair. {NAME} does not model that change; it says what
it fitted and over what. Each arc reports the share of the measured course its rows cover
(<code>fit_window_share</code>) and carries the <code>window_partial</code> caution when that is under a
half, because the model has no death term and the rows stop at the end of the plateau after the maximum.
An effect that appears only in late stationary phase is outside the window, not averaged into it.</p>
<p><strong>Interactions are pairwise and add up.</strong> The effect of j on i is the same whoever else is
in the vessel, and a community's dynamics are the sum of its pairs. Higher-order interactions, where a
third organism changes how the first two affect each other, have no term in this model and cannot be
fitted into one. {NAME} derives each arc from a pair, so a coefficient measured between two organisms is
carried into a simulation of any community as though it still held there. Where that is the question you
care about, a pairwise model is the wrong instrument rather than a model to be tuned.</p>
<p><strong>What to do about it.</strong> Read a simulation against the measurement it came from, as the
walkthrough below does, rather than against itself. Treat the coefficients as a description of the
organisms under the conditions that were fitted, and say which conditions those were: the medium travels
with every arc and with the carrying capacity for exactly this reason. Where it matters whether an
interaction is stable at all, the design that answers it is to run the same pair under more than one
environment and for long enough to reach late stationary phase, and to compare how the partner changes
the late abundances in each. That is a question about the organisms, not about the parameters, and it is
outside what {NAME} sets out to do: growth curves in, network out.</p>

<h2 id="glv-walkthrough">The gLV example, step by step</h2>
<p><strong>gLV example</strong> beside All fills both boxes and the one setting a package cannot be built
without, and runs the search, so the route above has something concrete to run on. It is one search of
one study, chosen by building the package of every study that yields one and scoring them: five give a
package of two organisms or more, three of those settle with every organism above zero, and this one is
the soundest of the three. Everything below is the generic route; only the numbers are this example's.</p>
<p>What makes it worth simulating, in the terms the package itself reports: each growth rate is the
median of three monoculture replicates that were all kept and all fitted a negative self-limitation, so
no plateau had to be substituted, and the steady state it predicts puts both organisms below their own
monoculture plateaus. What is thin about it is in the output too, and step 5 is where you find that
out.</p>
<ol>
<li><strong>Press gLV example.</strong> The first box fills with
<em>Bacteroides thetaiotaomicron</em> and <em>Roseburia intestinalis</em>, the second with
<code>SMGDB00000002</code> so nothing else is read, Report growth rates goes on, and the search runs. On
the command line the same run is
<code>grownet derive --live --species "Bacteroides thetaiotaomicron" "Roseburia intestinalis"
--conditions SMGDB00000002 --report-rates --glv glv.zip</code>.</li>
<li><strong>Read what came out</strong> before simulating anything. Two organisms and two arcs, each
inhibiting the other, which is the shape of a competition for one medium. The growth rates are 0.7981 /h
for <em>B. thetaiotaomicron</em> at a plateau of 9.13e8 Cells/mL and 0.6707 /h for
<em>R. intestinalis</em> at 7.01e8 Cells/mL, both fitted rather than measured, which
<code>capacity_source</code> in the rates file states. Both arcs carry the
<code>window_partial</code> caution: the rows cover about 0 to 30 of 120 measured hours, because the
model has no death term and these cultures decline after their peak. Neither arc reaches q below 0.05
(0.17 and 0.13), so this example shows a package being built and simulated, not an interaction being
established.</li>
<li><strong>Take the parameters.</strong> Either press <strong>Get gLV parameters</strong> for the zip,
or start R and press <strong>Send to R</strong>. The zip holds
<code>interaction_matrix.Cells_per_mL.csv</code>, <code>growth_rates.csv</code> and a
<code>README.txt</code> that states every formula, every unit and every caveat.</li>
<li><strong>In R:</strong>
<pre>install.packages("remotes")
{_e(R_INSTALL)}
if (!requireNamespace("BiocManager", quietly = TRUE)) install.packages("BiocManager")
BiocManager::install("miaSim")

library(grownet)
glv &lt;- grownet_listen()        # now press Send to R on the page
glv                            # 2 organisms, 1 matrix in Cells/mL, and the caveats

A &lt;- glv_matrix(glv)           # rows are affected, columns are the actor
r &lt;- glv_rates(glv)
A                              # B. thetaiotaomicron: -8.74e-10 on itself, -4.351e-10 from R. intestinalis
                               # R. intestinalis: -4.41e-10 from B. thetaiotaomicron, -9.571e-10 on itself
solve(A, -r)                   # where it settles: 7.323e8 and 3.634e8 Cells/mL, both above zero

args &lt;- as_miasim(glv)         # no scaling: these are coefficients, in 1/(time x abundance)
tse &lt;- do.call(miaSim::simulateGLV,
               c(args, list(x0 = c(1e6, 1e6), t_end = 120, t_step = 0.1,
                            stochastic = FALSE, migration_p = 0)))

x &lt;- SummarizedExperiment::assay(tse)
matplot(t(x), type = "l", lty = 1, xlab = "time (h)", ylab = "abundance (Cells/mL)")
legend("topright", legend = rownames(x), lty = 1, col = seq_len(nrow(x)), bty = "n")</pre></li>
<li><strong>Hold it against the measurement.</strong> This is the step to keep, whatever package you
build. Both organisms start at 1e6 Cells/mL and settle near the two numbers
<code>solve(A, -r)</code> prints, which only checks that the simulation and the package agree. Whether
the package agrees with the <em>data</em> is a separate question, and the co-culture it was fitted from
answers it: those curves peak near 2.4e8 and 2.3e8 Cells/mL, so the predicted steady state sits about
three times and about one and a half times above the measured peaks, in the same order, and the measured
cultures never held a steady state at all inside the window the fit used. A factor of a few in the same
order is what this model, fitted this way, is worth. Read any package this way before you trust it: a
prediction that inverts the ordering of the co-culture is telling you the fit absorbed something, and
<code>rate_mismatch_to_zero</code> on each arc says how small a mismatch in the monoculture rate would
account for it.</li>
<li><strong>If it does not settle</strong>, that is a result and the package says so before you run it:
a fit whose cells outweigh the organisms' own limitations has no bounded state, and the README names it.
Nothing in the package should be scaled to make a simulation behave, which is why
<code>glv_scale()</code> warns when it is called on fitted coefficients.</li>
</ol>
<p class="hint">The numbers above are what the database holds today. mGrowthDB changes, so a rerun can
give others; the report beside the download says what was read and when.</p>

<h2 id="settings">Advanced settings</h2>
<p>Every setting has a default that suits most searches. The command line takes the same settings.</p>
{settings}

<h2 id="attributes">Arc and node attributes</h2>
<p>Every downloaded network, JSON or GraphML, carries these for each arc (edge) and node. A network
names the format it speaks in its <code>schema</code> field, <code>grownet.interaction_network/v3</code>
since 0.3.0. It moved to <code>/v1</code> in 0.2.0 because <code>significance</code> changed meaning, from
the corrected p-value to -log10 of it, and to <code>/v2</code> and then <code>/v3</code> because optional
arc fields were added and an installed 0.2.0 builds its arcs from every field a file carries, so it must
read a newer daily network as a format it does not know and derive live instead. A file from 0.1.x says
<code>/v0</code> and one from 0.2.x <code>/v1</code>; both are still valid, read with their own meaning,
and so is <code>/v2</code>, which no release ever carried. The network
itself records the tool, <code>tool_version</code>, the date and time it was derived (<code>derived_on</code>,
<code>derived_at</code>), every setting used, and the version of the data: mGrowthDB publishes no version of
the whole database, so <code>meta.data</code> holds when it was read and each study's upload and
publication dates, which change when a study is corrected. A search run with Report growth rates also
carries <code>meta.growth_rates</code>: the rule the rates follow, a rate per organism with its unit, how
many monoculture replicates it rests on, the studies behind it and each study's own median, and
<code>without_a_rate</code>, the organisms that have none.</p>
{edges}
{nodes}

<h2 id="decisions">Why it works this way</h2>
<p>The main choices behind the method, each settled on the issue named (in the
<a href="{ISSUES}">issue tracker</a>).</p>
<ul class="decisions">{decisions}</ul>

<h2 id="cli">The command line</h2>
<p>The same search as the Example button, with three of the page's outputs: the network written to a file,
its report, and the network sent to Cytoscape:</p>
<pre>{_e(EXAMPLE_CLI)}</pre>
<p>Without installing anything, <code>uvx --from git+{REPOSITORY} {COMMAND} ...</code> runs the same
command. Other uses:</p>
<pre>{COMMAND} derive SMGDB00000004 --live --format graphml --out study4.graphml
{COMMAND} derive --live --species Blautia --conditions "Wilkins-Chalgren" --out wc.json
{COMMAND} derive SMGDB00000004 --live --format matrix --out study4_matrix.csv
{COMMAND} derive SMGDB00000004 --live --report-rates --rates study4_rates.csv --glv study4_glv.zip
{COMMAND} derive --live --species Bacteroides --all-partners --merge-genera --out bacteroides.json
{COMMAND} derive --live --all --merge-arcs --merge-genera --out all_genera.json
{COMMAND} gui
{COMMAND} validate example.json</pre>
<p>The first derives one whole study; the second searches a genus in one medium (the second box, from
the command line); the third writes a study as the adjacency matrix; the fourth adds the growth rates and
the gLV parameters (<a href="#glv">the matrix, the growth rates and gLV</a>); the fifth a genus, every
species of it with every partner, one node per genus; the sixth all of mGrowthDB, as the All button does,
merged across studies and then to genus; the seventh opens this page, and the last checks a file against
the format. Every advanced setting has its flag (see the list above), and
<code>{COMMAND} derive --help</code> lists them all. Besides those:</p>
<ul>{cli_only}</ul>

<h2 id="empty">No network came back</h2>
<ol>
<li>Look at the Species list at the top of the result. An entry under "Not used" gave nothing, and says why:
see <a href="#qa">the first question</a>.</li>
<li>"Studies searched: none" means no study in mGrowthDB holds those strains.</li>
<li>Open "pair(s) the data did not support": each line says why a pair gave no edge.</li>
<li>The usual reasons, and what to change:
<ul>
<li>the study grows the species only in a community that is neither a two-member co-culture nor a
drop-out design: grownet has no method for it yet;</li>
<li>no monoculture was grown under the same conditions: nothing to compare with;</li>
<li>the experiments are chemostats or serial dilutions: set the growth measure to max, which that mode
supports, or tick "Include chemostat and serial dilution experiments" to use them with another measure;</li>
<li>every edge is low quality: tick "Show low-quality edges";</li>
<li>every edge is below the absence threshold: open that section of the result, or set k to 0;</li>
<li>the partners are species you did not type: untick "Only interactions between the species
entered";</li>
<li>the second box is holding the search to a medium, an experiment or a study that these species were
not grown in: empty it, or try a shorter word, since a medium is matched as text (the result says how
many studies it left out).</li>
</ul></li>
</ol>

<h2 id="qa">Questions and problems</h2>
<dl class="qa">{qa}</dl>

<h2 id="cite">How to cite</h2>
<p>Cite the studies behind the edges you use: the Sources list under each result names every study with
its license, and each edge's <code>study_ids</code> say which ones it rests on. Cite grownet from its
<a href="{REPOSITORY}/blob/main/CITATION.cff">CITATION.cff</a>, with the version and date from the
network's <code>meta</code>.</p>

<h2 id="issues">Report a problem or ask for a feature</h2>
<p>Open an issue in the <a href="{ISSUES}">issue tracker</a> (<a href="{NEW_ISSUE}">new issue</a>).
Say what you searched, the settings, and the tool version shown next to the name. Problems with the data
itself are for mGrowthDB, since grownet shows the data as mGrowthDB holds it.</p>"""


def _default(value, key: str = "") -> str:
    if value is None and key == "max_adjusted_p":
        return "off"
    if value is None and key.startswith("no_growth_"):
        from . import interaction  # None means the rule's own default, read when used
        value = getattr(interaction, key.upper())
    if value is True:
        return "on"
    if value is False:
        return "off"
    if value == "":
        return "none"
    return str(value)


def render_about() -> str:
    """Who built the tool, where its source is, and what each release brought (#80, #112)."""
    log = "".join(
        f"<h3>{_e(version)} <span class=\"muted\">{_e(date)}</span></h3><ul>"
        + "".join(f"<li>{_e(line)}</li>" for line in lines) + "</ul>"
        for version, date, lines in RELEASES)
    return (f"<h2 class=\"page\">About {_e(NAME)}</h2><p>{_e(ABOUT)}</p>"
            f"<p>Source code, issues and license: <a href=\"{REPOSITORY}\">{REPOSITORY}</a></p>"
            f"<p>Version {_e(__version__)}.</p>"
            f"<h2>What changed</h2><p class=\"hint\">The short version. The full record is "
            f"<a href=\"{REPOSITORY}/blob/main/CHANGELOG.md\">CHANGELOG.md</a> in the repository.</p>"
            f"{log}")
