"""The help page of the local page (#78): settings, arc attributes, decisions, the command line, Q&A.

The content is data, keyed by the names the code uses, so the tests can require an entry for every
advanced setting (`gui.DEFAULTS`), every command line option of `derive`, and every node and edge field of
the model. Adding any of those without a line here fails the tests, the same way the legend works.
"""
from __future__ import annotations

import html

from . import __version__
from .brand import COMMAND, NAME

REPOSITORY = "https://github.com/crossfeed-bio/crossfeed"
ISSUES = f"{REPOSITORY}/issues"
NEW_ISSUE = f"{ISSUES}/new/choose"
MGROWTHDB = "https://mgrowthdb.gbiomed.kuleuven.be"

# key in gui.DEFAULTS -> (label on the page, command line flag, what it does and when to change it)
SETTINGS = {
    "metric": ("Growth measure", "--metric auc|max",
               "The growth property compared with and without the partner. The area under the curve (auc, "
               "the default) combines lag, rate and yield in one number; the maximal abundance (max) keeps "
               "yield only."),
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
                          "An edge is absent (no interaction found) when |log2 mean| < k times its standard "
                          "deviation. The default 1 means the mean plus or minus its sd stays on one side of "
                          "zero. Raise k for a stricter network; 0 marks nothing absent."),
    "correction": ("Multiple testing correction", "--correction bh|by",
                   "How the reported p-values are adjusted for the number of comparisons in one search: "
                   "Benjamini-Hochberg (default) or the more conservative Benjamini-Yekutieli, which holds "
                   "under any dependence between tests. The p-values support an edge; they decide nothing."),
    "spike_factor": ("Spike limit", "--spike-factor F",
                     "A replicate curve with one or two interior points more than F times above both "
                     "neighbors (default 100) is left out and reported, with the other measurements of the "
                     "same replicate named. 0 keeps every curve."),
    "no_growth_alpha": ("No-growth alpha", "--no-growth-alpha ALPHA",
                        "Before any ratio, each replicate set is checked for growth: a paired t-test on each "
                        "replicate's log2(maximum / first time point), the maximum taken at whatever time "
                        "that replicate peaks. A set that grew neither significantly at this level nor by the "
                        "factor below has not grown, which makes an edge obligate or abolished. 0 switches the "
                        "rule off."),
    "no_growth_factor": ("No-growth factor", "--no-growth-factor F",
                         "The rise that defines growth whatever the test says, as a geometric mean over "
                         "replicates. 1.5 is a medium default; 2 (one doubling) is more stringent. 0 leaves "
                         "the test alone."),
    "studies": ("Only these studies", "STUDY",
                "Comma separated mGrowthDB study ids to search, instead of every study holding the species; "
                "on the command line, the study argument given with --species. "
                "Use it to speed up a search or to reproduce one study's network."),
    "only_entered": ("Only interactions between the species entered", "--all-partners",
                     "On by default: an edge is kept when both ends are species you typed. Untick it, or give "
                     "--all-partners, to see every partner of your species in the studies found."),
}

# command line options of `derive` that are not advanced settings -> what they do
CLI_ONLY = {
    "--species": "species or strain names, or NCBI taxon ids: search every study holding them, as the page does",
    "--live": "fetch from the mGrowthDB API (the normal case)",
    "--fixture": "derive from a JSON list of interaction records instead (offline, for testing)",
    "--deriver": "plug in your own derivation method, given as module:ClassName (one study at a time)",
    "--format": "json (the neutral format, default) or graphml (Cytoscape, igraph, networkx, Gephi)",
    "--out": "write the network to a file instead of the screen",
    "--to-cytoscape": "also send the network into a running Cytoscape on this machine, with the legend's style",
    "--cytoscape-port": "the port Cytoscape's CyREST listens on (default 1234)",
}

# Edge field -> meaning. The GraphML attribute has the same name.
EDGE_ATTRIBUTES = {
    "source": "the organism whose presence is varied (node id)",
    "target": "the organism whose growth is measured (node id)",
    "effect": "facilitation (the target grows more with the source) or inhibition (less); neutral only "
              "in networks from the retired baseline",
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
    "metric": "the growth property compared: auc or max",
    "method": "how the edge was computed, in words",
    "quality": "flags that make the edge low quality: single_replicate, strains_pooled, non_batch, "
               "removed_member_detected; empty means no issue found",
    "cautions": "remarks that do not lower quality: two_replicates (exactly two replicates on a side)",
    "notes": "other remarks, for example a replicate left out for a spike",
    "evidence": "biculture (monoculture against a two-member co-culture: a direct interaction) or dropout "
                "(a community against the same community without the source: direct or indirect)",
    "community": "the members of the community a drop-out arc comes from",
    "condition": "the experiment the edge comes from; interactions are condition-specific",
    "cultivation_mode": "batch, chemostat, and so on, as mGrowthDB records it",
    "experiments": "the mGrowthDB experiments whose replicates the edge compares",
    "study_ids": "the studies supporting this edge; cite them (see Sources)",
}

# Node field -> meaning
NODE_ATTRIBUTES = {
    "id": "ncbi:<taxon id> for a strain with an NCBI taxon id, otherwise genus and species from the name",
    "name": "the strain name, as the study records it",
    "taxon_id": "the NCBI taxon id of the strain, as mGrowthDB records it",
    "species": "genus and species from the name, to merge with species-level networks",
    "identity": "what the id rests on: ncbi (the taxon id) or name",
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
    ("Experiments are pooled only when they are replicates.",
     "Interactions depend on the environment, so experiments with different conditions give parallel "
     "arcs, one each (#47)."),
    ("Batch culture only, by default.",
     "Chemostat and serial dilution curves measure a different quantity (#42)."),
    ("Suspect curves are flagged, never silently dropped or replaced.",
     "A replicate with an implausible spike is left out and reported, with the other techniques measured "
     "on it named (#39)."),
    ("grownet never corrects source data.",
     "Errors in mGrowthDB records are fixed in mGrowthDB, so every user sees the same data."),
    ("Everything runs on your machine.",
     "The page is served from 127.0.0.1 with a token, has no JavaScript, and the tool needs nothing beyond "
     "Python's standard library."),
)

# (question, answer as HTML)
QA = (
    ("A name is not recognized.",
     "Names are resolved through mGrowthDB's own strain records. Try the other name of a renamed species "
     "(Faecalibacterium prausnitzii or duncaniae), the strain name, or the NCBI taxon id."),
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
     "mGrowthDB gains and corrects data. Every network records the tool version and the date it was "
     "derived (tool_version, derived_on), so two files can be told apart."),
    ("How do I open the network in Cytoscape?",
     "Start Cytoscape, then press Send to Cytoscape under the result: the network arrives with the legend's "
     "style. Without the button, download GraphML and choose File, Import, Network from File in Cytoscape."),
    ("\"could not reach Cytoscape\".",
     "Cytoscape is not running, or its CyREST port is not 1234. Start Cytoscape and wait until it has "
     "opened, then press the button again."),
    ("How do I stop grownet?",
     "Press Ctrl+C in the terminal where it runs."),
)

EXAMPLE_CLI = (f'{COMMAND} derive --live --species "Faecalibacterium duncaniae" "Blautia hydrogenotrophica" '
               '--out example.json')


def _e(x) -> str:
    return html.escape(str(x), quote=True)


def _name(field: str) -> str:
    """A field name that may break after its underscores, and nowhere else, on a narrow screen."""
    return "<code>" + _e(field).replace("_", "_<wbr>") + "</code>"


def _table(head, rows) -> str:
    th = "".join(f"<th>{_e(h)}</th>" for h in head)
    return f"<table><tr>{th}</tr>" + "".join(rows) + "</table>"


SECTIONS = (("what", "What grownet does"), ("example", "Try the example"), ("reading", "Reading the result"),
            ("settings", "Advanced settings"), ("attributes", "Arc and node attributes"),
            ("decisions", "Why it works this way"), ("cli", "The command line"),
            ("empty", "No network came back"), ("qa", "Questions and problems"), ("cite", "How to cite"),
            ("issues", "Report a problem or ask for a feature"))


def render_help(token: str, defaults: dict, example: tuple) -> str:
    """The help page body. `defaults` is gui.DEFAULTS and `example` gui.EXAMPLE, passed in to keep this
    module free of the server."""
    t = _e(token)
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
    qa = "".join(f"<dt>{_e(q)}</dt><dd>{a}</dd>" for q, a in QA)
    cli_only = "".join(f"<li><code>{_e(k)}</code>: {_e(v)}</li>" for k, v in CLI_ONLY.items())
    pair = " and ".join(example)
    return f"""<h2 class="page">Help <span class="version">{NAME} {_e(__version__)}</span></h2>
<ol class="toc">{toc}</ol>

<h2 id="what">What grownet does</h2>
<p>Type species names, one per line, or NCBI taxon ids. grownet looks them up in mGrowthDB, reads the
growth curves of every study that holds them, and derives the interactions between them on this machine.
Nothing is uploaded, and nothing is written outside the file you download.</p>

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
<p><a href="/legend?token={t}">The legend</a> explains every line, arrowhead and flag.</p>

<h2 id="settings">Advanced settings</h2>
<p>Every setting has a default that suits most searches. The command line takes the same settings.</p>
{settings}

<h2 id="attributes">Arc and node attributes</h2>
<p>Every downloaded network, JSON or GraphML, carries these for each arc (edge) and node. The network
itself records the tool, <code>tool_version</code>, <code>derived_on</code> and every setting used, in
<code>meta</code>.</p>
{edges}
{nodes}

<h2 id="decisions">Why it works this way</h2>
<p>The main choices behind the method, each settled on the issue named (in the
<a href="{ISSUES}">issue tracker</a>).</p>
<ul class="decisions">{decisions}</ul>

<h2 id="cli">The command line</h2>
<p>The same search as the Example button, written to a file:</p>
<pre>{_e(EXAMPLE_CLI)}</pre>
<p>Without installing anything, <code>uvx --from git+{REPOSITORY} {COMMAND} ...</code> runs the same
command. The command is still called <code>{COMMAND}</code>: it becomes <code>{NAME}</code> when the package
is renamed (#71). Other uses:</p>
<pre>{COMMAND} derive SMGDB00000004 --live --format graphml --out study4.graphml
{COMMAND} gui
{COMMAND} validate example.json</pre>
<p>The first derives one whole study, the second opens this page, the third checks a file against the
format. Every advanced setting has its flag (see the list above), and <code>{COMMAND} derive --help</code>
lists them all. Besides those:</p>
<ul>{cli_only}</ul>

<h2 id="empty">No network came back</h2>
<ol>
<li>Look at the Species list at the top of the result. A name under "Not in mGrowthDB" was not found:
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
