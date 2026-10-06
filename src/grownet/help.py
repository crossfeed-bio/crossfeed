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
        "its own column. A network says it speaks grownet.interaction_network/v1 because of it.",
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
                        "species is not."),
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
                   "How the p-values of Welch's t-test are adjusted for multiple testing, over every "
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
                   "(EMGDB...), and naming a comparison keeps the monocultures it is made against. On the "
                   "command line a study id given this way replaces the study argument."),
    "exclude_studies": ("Exclude these studies", "--exclude-studies IDS",
                        "Comma separated mGrowthDB study ids that are never searched, for example a study "
                        "you know to be unsuitable. Empty by default. It applies after the second box, "
                        "so a study named in both is left out."),
    "only_entered": ("Only interactions between the species entered", "--all-partners",
                     "On by default: an edge is kept when both ends are species you typed. Untick it, or give "
                     "--all-partners, to see every partner of your species in the studies found."),
    "report_rates": ("Report growth rates", "--report-rates",
                     "Off by default, since a rate costs a fit per curve. With it on, every organism in the "
                     "network also gets its maximum specific growth rate in monoculture, the median over the "
                     "replicates and studies that have one, downloadable as its own CSV and used by the gLV "
                     "parameters. Batch monocultures only: in a chemostat the rate a curve shows is the "
                     "dilution rate. The gLV mode button turns it on."),
}

# command line options of `derive` that are not advanced settings -> what they do
CLI_ONLY = {
    "--glv-mode": "the page's gLV mode button, from the command line: --report-rates and --no-dropout "
                  "together, which is what a simulation needs",
    "--rates": "write the growth rates to a CSV file, the page's Download the growth rates (needs "
               "--report-rates)",
    "--glv": "write the parameters of a generalized Lotka-Volterra simulation to a zip file, the page's "
             "gLV parameters, Download (needs --report-rates)",
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
    "p_value": "Welch's t-test on the per-replicate log2 values, unadjusted",
    "q_value": "that p-value corrected for multiple testing over every comparison of the search, the q "
               "on the page (see How an interaction is decided)",
    "significance": "-log10 of the q-value: larger is stronger evidence, 0 at q = 1, and a style can map "
                    "it continuously. It is capped at 15 for a q-value of zero",
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
                "p-value filter on: the arc has no p-value, so the filter kept it without judging it)",
    "notes": "other remarks, for example a replicate left out for a spike",
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
must share. Every arc now records its <code>medium</code>, so a network says which environments it came
from.</p>

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
<p><strong>The p-value.</strong> Every arc with at least two replicates on each side is tested with Welch's
two-sided t-test on the per-replicate log2 values (<code>p_value</code>). The p-values are adjusted for
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
SMGDB00000007 failed that passed. The absence threshold judges each arc on its own data only.</p>
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
has no log2 ratio at all, because one side did not grow, so it carries +10 and an abolished one -10: a
stated extreme, past anything a measured comparison reaches, which the gLV README names cell by cell. Such
an arc never enters the median of the arcs that do have a ratio; it sets a cell only when no arc of that
pair was quantified. The diagonal of this matrix is 0; only the gLV package sets it to -1.</p>
<p><strong>The growth rates.</strong> With Report growth rates on, every organism in the network also
gets its maximum specific growth rate in monoculture: the method the Growth rate method setting names
(easylinear by default, the one mGrowthDB reports), the median over the replicates and studies that have
one, with each study's own median kept beside it in the network's meta. Batch monocultures only: in a
chemostat or a serial dilution the rate a curve shows is the dilution rate, and a rate from a co-culture
would be growth with a partner, which is the comparison, not the organism's own rate. An organism whose
curves give no rate is named on the page and in the report, never given a substitute number.</p>
<p><strong>Three more quantities travel with a rate</strong>, which is what a gLV coefficient is made of:
which estimator produced the rate; the <strong>lag</strong>, always from the Baranyi fit, the only
estimator that has one, whichever one produced the rate; and the organism's monoculture
<strong>carrying capacity</strong>, the plateau of its curves, taken only from curves certified to have
reached stationary phase and left in the abundance unit they were measured in. They are in
<code>growth_rates.csv</code>, in the network's meta and in the report, with every curve that gave no
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
and an off-diagonal cell is <code>A[i][j] = r_i (2^L - 1) / x_j</code> with L the log2 ratio of i's growth
rate with j over without it and x_j the partner's abundance over i's growth window;
<code>growth_rates.csv</code> (one rate per organism, in the same order, with how many values it rests on,
and beside it the estimator, the lag and the carrying capacity); and <code>README.txt</code>, which states
every formula and unit, names any pair left at 0 for disagreeing in sign, names every organism and every
effect that could not be fitted and why, and names the media the arcs were measured in: a simulation is of
one environment, so a package built from several media says so in capitals and points at the second box
(<a href="#where">choosing where to look</a>). Every cell is a per-capita effect in 1/(time x abundance),
so nothing in the package is a convention and nothing needs scaling to match the rest. Abundances are
never converted between units, which is why each unit has its own matrix: a cell mass conversion would
have to be invented, while the dynamics are the same in any unit. A simulation of these numbers can still
grow without bound and come back as NA, which now says something about the measurements, two organisms
fitted as facilitating each other more than each limits itself, rather than about a convention; the
equilibrium of a fit is the solution of A x = -r, and a negative entry there means the fit has no positive
steady state.</p>
<p>So a package needs the comparison to be on the <strong>growth rate</strong>: the area under the curve
and the maximum cannot produce the ratio L. gLV mode sets that, and without it the page says which
setting to change rather than converting the wrong quantity. Every cell of a row carries the factor
r_i, so the row divides by it: the rate estimator sets how fast a simulation moves and nothing about
where it settles, which is the solution of A x = -r.</p>

<p><strong>In R, with the companion package.</strong> The same control sends the parameters straight into
a running R session, which is what the R package in this project is for. It assumes no simulator: it
hands over a plain matrix and a plain vector, with a helper that shapes them for
<a href="https://bioconductor.org/packages/release/bioc/html/miaSim.html">miaSim</a>, whose
<code>simulateGLV</code> solves dx/dt = x(b + Ax), the order this matrix is written in.</p>
<p><strong>This route still carries the effect-size matrix</strong>, with -1 on the diagonal by convention
and +10 or -10 for an obligate or abolished pair: the numbers of a cell here are log2 means of a growth
comparison and are not fitted gLV coefficients, so they are scaled for a model rather than used unchanged,
which is what <code>glv_scale()</code> in the R package is for. That factor is a free parameter, not a
calibration: nothing in the growth data fixes the scale, so whoever simulates chooses it, and that choice,
rather than the measurements, sets where the simulation settles. Report the factor you used with any
result that depends on it. The zip above is the converted one; the conversion reaches this route and the
R package next (#120), and then the scaling goes with it.</p>
<pre>install.packages("remotes")
{_e(R_INSTALL)}
library(grownet)
glv &lt;- grownet_listen()        # then press Get gLV parameters, Send to R
glv                            # prints what it holds and what to read before simulating
A &lt;- glv_matrix(glv)           # warns about any cell that is a stated extreme
r &lt;- glv_rates(glv)

args &lt;- as_miasim(glv_scale(glv))
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

<h2 id="settings">Advanced settings</h2>
<p>Every setting has a default that suits most searches. The command line takes the same settings.</p>
{settings}

<h2 id="attributes">Arc and node attributes</h2>
<p>Every downloaded network, JSON or GraphML, carries these for each arc (edge) and node. A network
names the format it speaks in its <code>schema</code> field, <code>grownet.interaction_network/v1</code>
since 0.2.0: the version moved because <code>significance</code> changed meaning, from the corrected
p-value to -log10 of it. A file from 0.1.x says <code>/v0</code> and is still valid, read with the older
meaning. The network
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
