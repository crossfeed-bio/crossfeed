"""The help page of the local page (#78): settings, arc attributes, decisions, the command line, Q&A.

The content is data, keyed by the names the code uses, so the tests can require an entry for every
advanced setting (`gui.DEFAULTS`), every command line option of `derive`, and every node and edge field of
the model. Adding any of those without a line here fails the tests, the same way the legend works.
"""
from __future__ import annotations

import html

from . import __version__
from .brand import COMMAND, NAME
from .idea import idea_figure

REPOSITORY = "https://github.com/crossfeed-bio/crossfeed"
ISSUES = f"{REPOSITORY}/issues"
NEW_ISSUE = f"{ISSUES}/new/choose"
MGROWTHDB = "https://mgrowthdb.gbiomed.kuleuven.be"
# the local page's download of the Cytoscape style; the token is filled in when the page is written
STYLE_LINK = "/grownet_style.json?token=__TOKEN__"

# The About page (#80): the wording Craig agreed to on #80, naming both builders; change it only with
# their agreement.
ABOUT = (f"{NAME} was built by Karoline Faust (KU Leuven) and Craig Heilmann (Syntropa), working through "
         "their AI coding agents (Claude).")

# key in gui.DEFAULTS -> (label on the page, command line flag, what it does and when to change it)
SETTINGS = {
    "metric": ("Growth measure", "--metric auc|max|growth_rate",
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
                            "Low-quality edges carry a quality flag (pooled strains, a chemostat curve, a "
                            "drop-out whose removed member was still detected). They are computed but not "
                            "shown by default, and never read as an absence of interaction. Single-replicate "
                            "edges are always shown, flagged."),
    "include_dropout": ("Include drop-out communities", "--no-dropout",
                        "Arcs from a community compared with the same community without one member. On by "
                        "default; --no-dropout leaves them out. Such an arc says the removed member affects "
                        "the target, directly or through other members, so it is labeled evidence dropout."),
    "include_non_batch": ("Include chemostat and serial dilution experiments", "--include-non-batch",
                          "Off by default: under continuous dilution an area under the curve means something "
                          "else, so these curves are not comparable with batch curves. When included, their "
                          "edges carry the non_batch flag."),
    "absence_threshold": ("Absence threshold k", "--absence-threshold K",
                          "Decides when an interaction counts as absent, that is, when the data show the "
                          "species do not affect each other: its effect is small against its own spread, "
                          "|log2 mean| < k times the standard deviation. The default 1 means the mean plus "
                          "or minus its sd crosses zero. Raise k for a stricter network, where fewer "
                          "interactions count as present; 0 marks only a mean of exactly zero absent. Absent "
                          "interactions stay in the downloads with status absent."),
    "correction": ("Multiple testing correction", "--correction bh|by",
                   "How the reported p-values are adjusted for the number of comparisons in one search: "
                   "Benjamini-Hochberg (default) or the more conservative Benjamini-Yekutieli, which holds "
                   "under any dependence between tests. The p-values support an edge; they decide nothing."),
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
    "studies": ("Only these studies", "STUDY",
                "Comma separated mGrowthDB study ids to search, instead of every study holding the species; "
                "on the command line, the study argument given with --species. "
                "Use it to speed up a search or to reproduce one study's network."),
    "exclude_studies": ("Exclude these studies", "--exclude-studies IDS",
                        "Comma separated mGrowthDB study ids that are never searched, for example a study "
                        "you know to be unsuitable. Empty by default. It applies after Only these studies, "
                        "so a study named in both is left out."),
    "only_entered": ("Only interactions between the species entered", "--all-partners",
                     "On by default: an edge is kept when both ends are species you typed. Untick it, or give "
                     "--all-partners, to see every partner of your species in the studies found."),
}

# command line options of `derive` that are not advanced settings -> what they do
CLI_ONLY = {
    "--species": "species, strain or genus names, or NCBI taxon ids: search every study holding them, as the page "
                 "does",
    "--all": "every study in mGrowthDB, with every partner, as the page's All button (with --live)",
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
    "significance": "the p-value adjusted for multiple testing (see the correction setting)",
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
                "counts below detection)",
    "notes": "other remarks, for example a replicate left out for a spike",
    "evidence": "biculture (monoculture against a two-member co-culture: a direct interaction) or dropout "
                "(a community against the same community without the source: direct or indirect)",
    "community": "the members of the culture the arc comes from: the pair for a co-culture, the full "
                 "community for a drop-out arc",
    "condition": "the experiment the edge comes from; interactions are condition-specific",
    "cultivation_mode": "batch, chemostat, and so on, as mGrowthDB records it",
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
    ("Batch culture only, by default.",
     "Chemostat and serial dilution curves measure a different quantity (#42)."),
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
     f"<code>{COMMAND} style --out grownet_style.json</code>), import it in Cytoscape (File, Import, Styles "
     "from File) and choose grownet in the Style panel. The file holds every column the style maps (the "
     "line style, the width and the genus color)."),
    ("Gephi shows fewer arcs than the network has.",
     "A pair can have several arcs (one per condition or study). Gephi may merge parallel edges of one pair "
     "when it imports a file; the GraphML keeps every arc, and each carries its condition and study. Use "
     "Merge parallel arcs or Merge to genus to condense them on purpose, or read the arcs in the JSON."),
    ("The search is slow.",
     "Every study holding your species is fetched live from mGrowthDB. Name the studies you need under "
     "Only these studies."),
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
            ("example", "Try the example"), ("reading", "Reading the result"),
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
box and derives every study in mGrowthDB, with every partner. Nothing is uploaded, and nothing is written
outside the file you download.</p>

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
Choose it under Growth measure in the <a href="#settings">advanced settings</a>.</p>
<dl class="settings">
<dt>Area under the curve (auc, the default)</dt>
<dd>For: it combines lag, rate and yield in one number and uses every point of the curve, so it is robust
to noise in any one of them, and it is defined for any curve with two points. Against: it cannot say which
of lag, rate or yield changed; it needs the same time window on both sides, which grownet ensures; and it
counts the starting abundance too, so a larger inoculum raises it.</dd>
<dt>Maximal abundance (max)</dt>
<dd>For: the simplest to read, the yield a species reaches, and unaffected by a decline after the peak.
Against: it rests on one point, so one noisy measurement moves it, and it ignores timing, so a slow and a
fast grower reaching the same level look alike. It is misleading when one curve reached stationary phase
and the other did not; grownet then marks the arc <code>stationary_phase_differs</code>.</dd>
<dt>Growth rate (growth_rate)</dt>
<dd>For: the speed of growth, independent of yield and of the unit of abundance, and with easylinear the
same method mGrowthDB uses for the rates it reports. Against: it ignores yield and lag; it needs densely
sampled curves (at least 6 points), so a sparsely sampled study gives no rates at all; and it is
sensitive to noise in the steepest part of the curve. easylinear takes the steepest straight stretch of
log abundance and depends on its window; baranyi fits a growth model up to the end of the plateau, and
refuses curves the model does not describe, such as two growth phases.</dd>
</dl>

<h2 id="example">Try the example</h2>
<p>The Example button fills the box with {_e(pair)}, a pair with enough data to show a result: the
<a href="#cli">command line</a> section runs the same search.</p>

<h2 id="reading">Reading the result</h2>
<p>Each row is one directed interaction: a source species, the species it affects, the direction, and the
mean log2 difference with its standard deviation. An interaction counts as present when the effect is at
least k standard deviations of its own spread, with k the absence threshold. The adjusted p-value is
shown as support and decides nothing. Results are provisional: with two or three replicates, more
experiments can change any of them.</p>
<p>While a search runs, a progress bar shows which study is being read, and the page updates by itself.
The result then appears under the settings that produced it, so you can change a setting and search
again. Three buttons sit above the table: <strong>Download network</strong>, with the format (JSON or
GraphML) in the menu next to it; <strong>Send to Cytoscape</strong>, into a Cytoscape running on this
machine, in the legend's style; and <strong>Report</strong>, which opens the detailed comments of the
search (every setting, every interaction, every pair the data did not support, the sources) and
downloads them as a text file, with the tool version.</p>
<p><a href="/legend?token={t}{legend_job}">The legend</a> explains every line, arrowhead and flag.</p>

<h2 id="settings">Advanced settings</h2>
<p>Every setting has a default that suits most searches. The command line takes the same settings.</p>
{settings}

<h2 id="attributes">Arc and node attributes</h2>
<p>Every downloaded network, JSON or GraphML, carries these for each arc (edge) and node. The network
itself records the tool, <code>tool_version</code>, the date and time it was derived (<code>derived_on</code>,
<code>derived_at</code>), every setting used, and the version of the data: mGrowthDB publishes no version of
the whole database, so <code>meta.data</code> holds when it was read and each study's upload and
publication dates, which change when a study is corrected.</p>
{edges}
{nodes}

<h2 id="decisions">Why it works this way</h2>
<p>The main choices behind the method, each settled on the issue named (in the
<a href="{ISSUES}">issue tracker</a>).</p>
<ul class="decisions">{decisions}</ul>

<h2 id="cli">The command line</h2>
<p>The same search as the Example button, with the page's three outputs: the network written to a file,
its report, and the network sent to Cytoscape:</p>
<pre>{_e(EXAMPLE_CLI)}</pre>
<p>Without installing anything, <code>uvx --from git+{REPOSITORY} {COMMAND} ...</code> runs the same
command. Other uses:</p>
<pre>{COMMAND} derive SMGDB00000004 --live --format graphml --out study4.graphml
{COMMAND} derive --live --species Bacteroides --all-partners --merge-genera --out bacteroides.json
{COMMAND} derive --live --all --merge-arcs --merge-genera --out all_genera.json
{COMMAND} gui
{COMMAND} validate example.json</pre>
<p>The first derives one whole study; the second a genus, every species of it with every partner, one
node per genus; the third all of mGrowthDB, as the All button does, merged across studies and then to
genus; the fourth opens this page, and the last checks a file against the format. Every advanced setting
has its flag (see the list above), and <code>{COMMAND} derive --help</code>
lists them all. Besides those:</p>
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
<li>the experiments are chemostats: tick "Include chemostat and serial dilution experiments";</li>
<li>every edge is low quality: tick "Show low-quality edges";</li>
<li>every edge is below the absence threshold: open that section of the result, or set k to 0;</li>
<li>the partners are species you did not type: untick "Only interactions between the species
entered".</li>
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
    """Who built the tool, and where its source, issues and license are (#80)."""
    return (f"<h2 class=\"page\">About {_e(NAME)}</h2><p>{_e(ABOUT)}</p>"
            f"<p>Source code, issues and license: <a href=\"{REPOSITORY}\">{REPOSITORY}</a></p>"
            f"<p>Version {_e(__version__)}.</p>")
