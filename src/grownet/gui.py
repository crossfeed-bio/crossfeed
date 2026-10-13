"""A local page: type species names, get their interaction network.

`grownet gui` starts a small server from the standard library on 127.0.0.1, with a random token in the
URL, and opens the browser. Nothing is hosted, nothing is uploaded, and the page has no JavaScript: the
form posts back and the server returns HTML rendered in Python. Settings live in an HTML `details` block
("Advanced settings"), so the plain page is a box for species and a button.

The work is in `run_query`, which is pure apart from the client it is given: names to taxon ids
(grownet.taxonomy), taxon ids to studies (mGrowthDB search), then the existing derivation per study.
Rendering is in `render_form` and `render_result`, so both are testable without a socket.
"""
from __future__ import annotations

import dataclasses
import html
import http.server
import json
import math
import secrets
import socketserver
import threading
import time
import urllib.parse
import webbrowser
from collections import Counter

from . import __version__, brand, integrated, interaction, matrix, rates, rbridge, steady
from . import help as help_page
from . import published as daily
from . import selection as selecting
from .adapter import about_a_pair, condensed, unread
from .attribution import studies_with_edges
from .cytoscape import CytoscapeError, send, style_xml
from .derive import (
    ABSENCE_THRESHOLD,
    ABSENT,
    CAPACITY_MAX_FALL,
    PROVISIONAL,
    derive_interactions,
    genus_species,
    growth_rates,
    output_meta,
)
from .export import to_graphml
from .growth import SPIKE_FACTOR
from .legend import legend_svg
from .mgrowthdb import MGrowthDBError, data_versions, records_to_network
from .report import report_text
from .taxonomy import TAXON_ID, resolve_species, species_index, split_entries

TITLE = brand.NAME
# species that derive a non-empty network, for the Example button (Karoline's proposal, #73). The first is
# taxon 411483, which mGrowthDB holds under both its names after the 2022 reclassification.
# Three organisms that are grown together in mGrowthDB and whose arcs the shipped default can fit. The
# pair this was until 0.3.0, the first two, now gives nothing: what those two hold between them is a
# drop-out comparison inside a three-member community, and the integrated form does not fit a row from a
# community of three or more (Craig declined that on #127), so the button that is supposed to show the
# tool working showed an empty network. Adding the partner they are actually grown with is the smallest
# change that keeps the biology and the studies: measured live on 2026-10-09, three arcs over three
# organisms, against none (Karoline, 2026-10-09).
EXAMPLE = ("Faecalibacterium duncaniae", "Blautia hydrogenotrophica", "Roseburia intestinalis")
EXAMPLE_MESSAGE = ("Example: three species that are grown together, with every setting back to its "
                   "default. Press Find interactions.")
# A search that gives a gLV package anyone can simulate, chosen by building the package of every study
# that yields one and scoring them (2026-10-07, Karoline: "include a gLV example button in the GUI that
# configures everything for a working gLV example"). Five studies give a package of two organisms or
# more, three of those settle with every organism above zero, and SMGDB00000002 is the soundest of the
# three: each rate is the median of three monoculture replicates that were all kept and all fitted a
# negative self-limitation (0.777, 0.859, 0.798 and 0.673, 0.671, 0.634 per hour), no capacity had to be
# substituted, and the equilibrium puts both organisms below their own monoculture plateaus in the order
# the co-culture measured.
#
# It replaced SMGDB00000006, the yoghurt pair, which was wrong on all three counts: of S. thermophilus's
# three monoculture replicates two were refused for a negative rate and the third was kept at 0.0109 /h,
# a 64 hour doubling time for a dairy starter, while all three fitted a POSITIVE self-limitation and so
# failed the same way; its plateau had to be taken from one measured curve; and the equilibrium inverted
# the co-culture it was fitted from by about 90 times (2026-10-07, #155 item 13).
GLV_EXAMPLE = ("Bacteroides thetaiotaomicron", "Roseburia intestinalis")
GLV_EXAMPLE_STUDY = "SMGDB00000002"
METRICS = ("auc", "max", "growth_rate")
DERIVATIONS = ("replicate", "integrated")


def metric_name(s: dict) -> str:
    """The metric a derivation runs on: auc, max, or the growth rate with its rule
    ("growth_rate:easylinear:5"), which is also what each edge records (#41)."""
    if s.get("metric") == "growth_rate":
        return rates.method_name(s.get("rate_method", rates.DEFAULT_METHOD),
                                 s.get("rate_window", rates.DEFAULT_WINDOW))
    return s.get("metric", "auc")


# one of each kind the box takes, shown above it (the box itself starts empty; Karoline, 2026-09-27),
# a genus among them (Karoline, 2026-09-28)
INPUT_EXAMPLES = ("Blautia hydrogenotrophica", "Faecalibacterium duncaniae A2-165", "Bacteroides", "411483")
DEFAULTS = {"metric": "auc", "rate_method": rates.DEFAULT_METHOD, "rate_window": rates.DEFAULT_WINDOW,
            "spike_factor": SPIKE_FACTOR, "absence_threshold": ABSENCE_THRESHOLD,
            # how far a certified curve may have fallen from its peak and still give a carrying capacity
            # (Karoline, 2026-10-07, closing open decision 4 of #141: "the factor ... should go in the
            # advanced settings. please choose a sensible default for it"). See derive.CAPACITY_MAX_FALL
            # for the measurement behind the 10.
            "capacity_max_fall": CAPACITY_MAX_FALL,
            "include_low_quality": False, "include_absent": False, "correction": "bh",
            # off by default: a rate costs a fit per monoculture curve, and most searches do not need
            # one. The gLV mode button turns it on (Karoline, 2026-10-04)
            "report_rates": False,
            # off by default too: the check reads the curves of chemostats the search never needed (#125)
            "steady_check": False,
            # The specified comparison of replicate sets, and gLV mode selects the integrated form
            # instead (Karoline, 2026-10-10). Each answers a different question and neither is the
            # stricter version of the other.
            #
            # A NETWORK is what this default reports, and the comparison is the only form that can
            # express two of its kinds of evidence: an arc from a community compared with the same
            # community without one member, and the no-growth rule's censored arcs with their measured
            # bounds. The integrated form refuses a community of three or more (Craig on #127), so no
            # drop-out arc can exist under it, and it has no no-growth rule at all. On the whole corpus
            # that is 145 arcs against 12, 122 of them drop-out, and 12 censored bounds against none
            # (measured 2026-10-09).
            #
            # A gLV COEFFICIENT is what gLV mode reports, and there the integrated form is the right one
            # for the reason Karoline gave on 2026-10-06: a coefficient from the comparison is a
            # difference of two separately fitted rates divided by one partner mean, which carries the
            # organism's own density as a confound. That argument is about the coefficient, and the
            # comparison that settled it was run in gLV mode (`--glv-mode`), where drop-out communities
            # are off on both sides, so it could not see what the default costs a network.
            "derivation": "replicate",
            "include_dropout": True,
            "include_non_batch": False, "conditions": "", "exclude_studies": "", "only_entered": True,
            "merge_arcs": False, "min_studies": 1, "merge_genera": False,
            # None: the no-growth rule's own defaults, read when used (grownet.interaction.grew)
            "no_growth_alpha": None, "no_growth_factor": None,
            # None: the q-value filter is off (register item 31)
            "max_adjusted_p": None}
# the threshold the filter offers when it is switched on (Karoline, 2026-09-30: "Settable, 0.05 default")
ADJUSTED_P_DEFAULT = 0.05
MISMATCH = ("Monoculture and co-culture growth were measured by different techniques in some of these "
            "studies, so neither the magnitude nor, near zero, the direction of those interactions is fully "
            "dependable.")
EMPTY_HELP = ("grownet derives interactions from pairwise (two-member) co-cultures and from drop-out "
              "designs (a community plus the same community without one member). Other larger communities "
              "yield nothing until a method suited to their design is chosen.")




def _job_suffix(job: str) -> str:
    """The query part that keeps a search with a link: "&job=<id>", or "" when no search is shown."""
    return f"&job={urllib.parse.quote(job)}" if job else ""


def _back(token: str, job: str = "", top: bool = False) -> str:
    """The Back button of Legend, Help and About: to the search they were opened from, when there is one, so
    its result is still there (Karoline, audit step 8, 2026-09-28: Help and back lost the result). With
    `top`, the one at the page's upper right, so a long page need not be scrolled to its end (Karoline,
    2026-09-28: "a top button Back would help in the right upper corner of the help page")."""
    href = f"/?token={token}{_job_suffix(job)}" + ("#result" if job else "")
    kind = "bar backtop" if top else "bar"
    return f"<p class=\"{kind}\"><a class=\"btn\" href=\"{html.escape(href, quote=True)}\">Back</a></p>"


def _page(body: str, token: str = "", refresh: str = "", job: str = "") -> str:
    """A page in the grownet style: a header with the mark, the name, the version, Legend, Help and About.
    `job` is the search the page shows, which Legend, Help, About and the mark carry, so each of them leads
    back to it (Karoline, 2026-09-28: the mark once led to an empty page); a new search is run from the form
    that is always on the page."""
    t = html.escape(token, quote=True)
    j = html.escape(_job_suffix(job), quote=True)
    icon = urllib.parse.quote(brand.logo_svg(64))
    mark = f"/?token={t}{j}"          # the top of the page: the settings, and the result under them
    header = (f"<header><a class=\"brand\" href=\"{mark}\"><h1 class=\"brand\">{brand.logo_svg(28)}"
              f"{brand.WORDMARK}</h1></a>{HEADING}"
              f"<nav><a class=\"btn quiet\" href=\"/legend?token={t}{j}\">Legend</a>"
              f"<a class=\"btn quiet\" href=\"/help?token={t}{j}\">Help</a>"
              f"<a class=\"btn quiet\" href=\"/about?token={t}{j}\">About</a></nav></header>")
    # a running search reloads its page every second (#75): a meta refresh, so no JavaScript is needed
    reload = f"<meta http-equiv=\"refresh\" content=\"1; url={html.escape(refresh, quote=True)}\">" if refresh else ""
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>{TITLE}</title>"
            f"{reload}<link rel=\"icon\" href=\"data:image/svg+xml;utf8,{icon}\">"
            f"<style>{brand.CSS}</style></head><body><div class=\"app\">{header}"
            # the name is all lowercase, so in prose it is marked as a name (Karoline, 2026-10-03); the
            # header's wordmark, commands and the title are left alone by in_prose
            f"<main>{brand.in_prose(body)}</main></div>"
            "</body></html>\n")


def _esc(x) -> str:
    return html.escape(str(x), quote=True)


HEADING = f"<span class=\"version\">{html.escape(__version__)}</span>"


def _settings_block(settings: dict, token: str = "", job: str = "") -> str:
    """Every setting, collapsed behind one button. The plain page shows species and a submit button."""
    s = {**DEFAULTS, **settings}
    why = f"/help?token={_esc(token)}{_esc(_job_suffix(job))}#statistics"
    p_filter = " checked" if s["max_adjusted_p"] is not None else ""
    p_value = _esc(s["max_adjusted_p"] if s["max_adjusted_p"] is not None else ADJUSTED_P_DEFAULT)
    checked = " checked" if s["only_entered"] else ""
    low = " checked" if s["include_low_quality"] else ""
    rates_on = " checked" if s["report_rates"] else ""
    steady_on = " checked" if s.get("steady_check") else ""
    dropout = " checked" if s["include_dropout"] else ""
    absent = " checked" if s["include_absent"] else ""
    non_batch = " checked" if s["include_non_batch"] else ""
    corrections = "".join(f"<option value=\"{c}\"{' selected' if s['correction'] == c else ''}>{label}</option>"
                          for c, label in (("bh", "Benjamini-Hochberg"), ("by", "Benjamini-Yekutieli")))
    options = "".join(f"<option value=\"{m}\"{' selected' if s['metric'] == m else ''}>{m}</option>"
                      for m in METRICS)
    derivations = "".join(f"<option value=\"{d}\"{' selected' if s.get('derivation', 'replicate') == d else ''}>"
                          f"{d}</option>" for d in DERIVATIONS)
    rate_methods = "".join(f"<option value=\"{m}\"{' selected' if s['rate_method'] == m else ''}>{m}</option>"
                           for m in rates.METHODS)
    # Open, with a count, when anything is not at its default. It was always collapsed and the result
    # section said nothing about a changed setting unless the network came out EMPTY, because
    # `_settings_to_try` runs only from `_empty_reason`: so the one case where numbers leave the page
    # under a changed threshold was the case the page did not mark (#250).
    changed = [k for k, v in s.items() if k in DEFAULTS and v != DEFAULTS[k]]
    head = ("<details>\n<summary>Advanced settings</summary>" if not changed else
            f"<details open>\n<summary>Advanced settings: {len(changed)} not at "
            f"{'its' if len(changed) == 1 else 'their'} default</summary>")
    return f"""{head}
<div class="row"><label>Growth property
  <select name="metric">{options}</select></label>
  <span class="muted">the growth property compared: auc, the area under the curve (default); max, the maximal
  abundance; or growth_rate, the maximum specific growth rate</span></div>
<div class="row"><label>Growth rate method
  <select name="rate_method">{rate_methods}</select></label>
  <span class="muted">with growth_rate: easylinear (default), the steepest part of the log curve, as mGrowthDB
  computes the rates it reports; or baranyi, a fitted growth model, where a curve the model does not describe
  is left out and reported</span></div>
<div class="row"><label>Derivation
  <select name="derivation">{derivations}</select></label>
  <span class="muted">replicate (the default), the specified comparison: a growth property of the
  replicates with the partner against those without it, and the only one that gives a drop-out arc or a
  censored one. Or integrated, which gLV mode selects and which fits each organism's row from the whole time
  course, ln(x_i(T) / x_i(0)) = r_i T + sum_j A_ij integral(x_j dt), over its growth phase; it needs no
  growth property and gives the gLV coefficients directly, and it reports every row its design cannot
  identify</span></div>
<div class="row"><label>Growth rate window
  <input name="rate_window" type="text" size="6" value="{_esc(s['rate_window'])}"></label>
  <span class="muted">with easylinear: the points in each fitted window (default 5, as mGrowthDB)</span></div>
<div class="row"><label><input type="checkbox" name="report_rates" value="1"{rates_on}>
  Report growth rates</label>
  <span class="muted">each organism's maximum specific growth rate in monoculture, as its own download and
  as the rates a gLV simulation takes; off by default, since a rate costs a fit per curve. gLV mode turns
  it on</span></div>
<div class="row"><label><input type="checkbox" name="steady_check" value="1"{steady_on}>
  Check against chemostat steady states</label>
  <span class="muted">score the gLV parameters against the steady states mGrowthDB holds for these
  organisms in continuous culture: a chemostat satisfies A x = -(r - D) there and was never used to fit
  them. Needs Report growth rates, and reads curves the search did not need</span></div>
<div class="row"><label><input type="checkbox" name="include_dropout" value="1"{dropout}>
  Include drop-out communities</label>
  <span class="muted">arcs from a community compared with the same community without one member, labeled
  evidence dropout; on by default. Such an arc may act through a third species, so gLV mode unticks it.
  It applies to the default derivation only: the integrated form, which gLV mode selects, refuses a
  community of three or more, so under that form this setting changes nothing</span></div>
<div class="row"><label><input type="checkbox" name="include_low_quality" value="1"{low}>
  Show low-quality edges</label>
  <span class="muted">pooled strains, a chemostat curve, or a drop-out whose removed member was still detected;
  single-replicate edges are always shown, flagged</span></div>
<div class="row"><label><input type="checkbox" name="include_absent" value="1"{absent}>
  Include arcs below the absence threshold</label>
  <span class="muted">off by default, so the downloads and Cytoscape hold exactly the interactions this
  page counts; on, they also carry the arcs the threshold marked absent, which lets you move k in
  Cytoscape on the effect_over_sd column without searching again</span></div>
<div class="row"><label><input type="checkbox" name="include_non_batch" value="1"{non_batch}>
  Include chemostat and serial dilution experiments</label>
  <span class="muted">with the growth measure max they are derived anyway, since the level a continuous
  culture settles at is comparable with and without a partner; with auc or a growth rate they are left out
  unless this is ticked, and such arcs are then marked low quality</span></div>
<div class="row"><label>Absence threshold k
  <input name="absence_threshold" type="text" size="6" value="{_esc(s['absence_threshold'])}"></label>
  <span class="muted">an interaction counts as absent (the species do not affect each other) when its
  effect is small against its spread: |log2 mean| &lt; k &times; sd. 1 means the mean &plusmn; sd crosses
  zero; 0 marks only a mean of exactly zero absent</span></div>
<div class="row"><label>Multiple testing correction
  <select name="correction">{corrections}</select></label>
  <span class="muted">how the p-values of the test the derivation ran are adjusted: Benjamini-Hochberg (default) or the
  more conservative Benjamini-Yekutieli. The adjustment runs across every comparison of this search
  together: all arcs of all the studies it reads, absent and low-quality ones included, not study by study.
  So an arc's q-value can change with the other studies a search reads (All reads every
  study)</span></div>
<div class="row"><label><input type="checkbox" name="filter_adjusted_p" value="1"{p_filter}>
  Filter on the q-value, at most
  <input name="max_adjusted_p" type="text" size="6" value="{p_value}"></label>
  <span class="muted">also leave out interactions whose q-value is above this; arcs without a p-value
  are kept, marked untested. Off by default: with two or three replicates the test misses many real effects,
  and a q-value depends on the other comparisons in the same search
  (<a href="{why}">why</a>)</span></div>
<div class="row"><label>Spike limit
  <input name="spike_factor" type="text" size="6" value="{_esc(s['spike_factor'])}"></label>
  <span class="muted">leave out a curve with one or two points this many times above both neighbors;
  0 keeps all</span></div>
<div class="row"><label>Carrying capacity decline limit
  <input name="capacity_max_fall" type="text" size="6" value="{_esc(s['capacity_max_fall'])}"></label>
  <span class="muted">a monoculture that grew, peaked and then declined has stopped growing, and its
  plateau is recorded as the peak; leave out a curve that ends below 1/this of its peak, where the peak
  was not a level the culture held; 0 keeps every certified plateau</span></div>
<div class="row"><label>No-growth alpha
  <input name="no_growth_alpha" type="text" size="6" value="{_esc(_no_growth(s, 'alpha'))}"></label>
  <span class="muted">before any comparison, grownet checks that a species grew: across the replicate
  growth curves of that species in one culture condition, the rise from the first time point to the
  maximum is tested (paired t-test). Not significant at this level, and below the factor: no growth. 0
  switches the check off</span></div>
<div class="row"><label>No-growth factor
  <input name="no_growth_factor" type="text" size="6" value="{_esc(_no_growth(s, 'factor'))}"></label>
  <span class="muted">replicate growth curves that rose at least this many times (geometric mean over the
  replicates) count as growth whatever the test says; 1.5 by default, 2 is stricter, 0 leaves the test
  alone</span></div>
<div class="row"><label><input type="checkbox" name="merge_arcs" value="1"{" checked" if s["merge_arcs"] else ""}>
  Merge parallel arcs</label>
  <span class="muted">one arc per source and target, across conditions and studies, with the median log2 mean
  and its range; arcs whose signs disagree are not merged. Off by default: interactions are
  condition-specific</span></div>
<div class="row"><label><input type="checkbox" name="merge_genera" value="1"{" checked" if s["merge_genera"] else ""}>
  Merge to genus</label>
  <span class="muted">one node per genus, and the arcs between two genera merged by sign, with the median log2
  mean and the number of species pairs behind each arc (strain pairs when only taxon ids were entered).
  Works with Merge parallel arcs, which then counts a pair measured in several studies once. Off by
  default</span></div>
<div class="row"><label>Minimum supporting studies
  <input name="min_studies" type="text" size="6" value="{_esc(s['min_studies'])}"></label>
  <span class="muted">keep arcs resting on at least this many studies; above 1 it needs merged arcs, since an
  unmerged arc rests on one study</span></div>
<div class="row"><label>Exclude these studies
  <input name="exclude_studies" type="text" size="40" value="{_esc(s['exclude_studies'])}"></label>
  <span class="muted">comma separated study ids never searched, for example a study you know to be
  unsuitable; empty by default</span></div>
<div class="row"><label><input type="checkbox" name="only_entered" value="1"{checked}>
  Only interactions between the species entered</label></div>
</details>"""


def render_form(token: str, entries: str = "", settings: dict | None = None, message: str = "",
                below: str = "", refresh: str = "", job: str = "", conditions: str = "") -> str:
    """The one page (#74): the species box, the settings, and under them whatever the search produced.

    `below` is the progress of a running search or its result, so the settings that produced a result stay
    on the page above it and can be changed and run again.
    """
    note = f"<p class=\"note\">{_esc(message)}</p>" if message else ""
    on = glv_mode_on(settings or {})
    glv_on, glv_pressed = (" on" if on else ""), ("true" if on else "false")
    return _page(f"""{note}<form method="post" action="/run?token={_esc(token)}">
<div class="boxes">
<div class="box">
<label class="field" for="species">Species, strains, genera or NCBI taxon ids</label>
<p class="examples">For example: {" &middot; ".join(_esc(x) for x in INPUT_EXAMPLES)}</p>
<textarea id="species" name="species" rows="5">{_esc(entries)}</textarea>
<p class="hint">One per line (a genus alone stands for all its species), or press Example. Interactions are
derived from mGrowthDB growth data on this machine; nothing is uploaded.</p>
</div>
<div class="box">
<label class="field" for="conditions">Media, experiments or studies (optional)</label>
<p class="examples">For example: {" &middot; ".join(_esc(x) for x in selecting.EXAMPLES)}</p>
<textarea id="conditions" name="conditions" rows="5">{_esc(conditions)}</textarea>
<p class="hint"><strong>All reads this box.</strong> A study or medium left here narrows All to it, which
is deliberate, so clear it to derive the whole of mGrowthDB; the gLV example button fills it and leaves it
filled (#193).
One per line. A medium is matched as text, so "wilkins" finds every spelling of
Wilkins-Chalgren <em>and</em> every variant of it: a medium with a sugar added or a carbon source left out
is another environment, so those stay apart and the report names every medium the search read. An id
(SMGDB..., EMGDB...) picks that study or experiment, which is how to read one medium alone. Empty means
every medium.</p>
</div>
</div>
<div class="bar"><button class="primary" type="submit">Find interactions</button>
<button type="submit" name="example" value="1">Example</button>
<button type="submit" name="all" value="1">All</button>
<button type="submit" name="glv_example" value="1">gLV example</button>
<button type="submit" name="glv_mode" value="1" class="switch{glv_on}" aria-pressed="{glv_pressed}"
><span class="track"><span class="knob"></span></span>gLV mode</button>
<span class="muted">All derives every study, ignoring the species box (half a minute). gLV example fills
the boxes and settings for a package that simulates, and runs it. gLV mode sets the four settings a
package needs, the derivation among them; press it again to switch back.</span></div>
{_settings_block(settings or {}, token, job)}
</form>{below}""", token, refresh, job)


def render_token_page(had_token: bool, port: int) -> str:
    """What someone sees who opens the page without the token, or with one from an earlier run."""
    what = ("That link carries a token from an earlier run of grownet, so it no longer opens this one."
            if had_token else
            "This page opens from the link grownet printed when it started, which carries a one-time "
            "token for this run.")
    return _page(f"""<h2 class="page">grownet is running on this machine</h2>
<p>{what}</p>
<p class="hint">Where to find the link: the terminal window where grownet was started prints
<code>grownet is at http://127.0.0.1:{int(port)}/?token=...</code>. Copy that whole line into the browser.
If the window is gone, stop grownet there with Ctrl+C and run <code>{_esc(brand.COMMAND)} gui</code>
again, which opens the browser for you.</p>
<p class="hint">The token is what keeps another program on this machine from driving the tool, so this
page does not show it.</p>""")


def render_progress(token: str, job: dict) -> str:
    """A search still running (#75): a progress bar, and a page that reloads itself until the result is
    ready. No JavaScript: the refresh is a meta element, the bar the native progress element."""
    done, total = job.get("done", 0), job.get("total")
    bar = (f"<progress max=\"{total}\" value=\"{done}\"></progress>" if total
           else "<progress></progress>")                      # no value: the browser shows it as busy
    below = (f"<section class=\"result\" id=\"result\"><h2>Searching</h2>{bar}"
             f"<p class=\"hint\">{_esc(job.get('message', ''))}</p>"
             "<p class=\"hint\">This page updates by itself until the result is ready.</p></section>")
    return render_form(token, "\n".join(job["entries"]), job["settings"], below=below,
                       conditions=(job["settings"] or {}).get("conditions", ""),
                       refresh=f"/?token={token}&job={job['id']}", job=job["id"])


def render_legend(token: str, job: str = "") -> str:
    """The legend inside the page frame, so every page carries the same header."""
    return _page(_back(token, job, top=True) + f"<div class=\"legend\">{legend_svg()}</div>" + _back(token, job),
                 token, job=job)


def render_help(token: str, job: str = "") -> str:
    return _page(_back(token, job, top=True) + help_page.render_help(token, DEFAULTS, EXAMPLE, job=job)
                 + _back(token, job), token, job=job)


def render_about(token: str, job: str = "") -> str:
    return _page(_back(token, job, top=True) + help_page.render_about() + _back(token, job), token, job=job)


# "sign" rather than "direction": the arc already has a direction, from the source to the species it
# affects, so the word was taken (Karoline, 2026-10-03)
HEADER = ("<tr><th>source</th><th>affects</th><th>sign</th><th>log2 mean &plusmn; sd</th>"
          "<th>|mean| / sd</th><th>replicates with / without</th><th>q</th><th>condition</th>"
          "<th>remarks</th><th>study</th></tr>")


def _direction(e) -> str:
    """The effect, with obligate and abolished named, since they are the extremes of each direction."""
    if e.outcome == "obligate":
        return "facilitation (obligate)"
    if e.outcome == "abolished":
        return "inhibition (abolished)"
    return e.effect


# A number that was never computed is missing, not zero and not blank: a blank cell reads as an oversight,
# and zero would read as the strongest possible q-value (Karoline, 2026-10-03). The page says so in words.
MISSING = "<span class=\"muted\" title=\"not computed for this arc\">not computed</span>"


def _number(x, fmt: str, missing: str = "") -> str:
    return missing if x is None else format(x, fmt)


def _arc_rows(net, edges) -> str:
    rows = []
    for e in edges:
        # flags and cautions as quiet pills; free-text notes as plain text after them
        pills = [*(["drop-out community, possibly indirect"] if e.evidence == "dropout" else []),
                 *(f"low quality: {q.replace('_', ' ')}" for q in e.quality),
                 *(f"caution: {c.replace('_', ' ')}" for c in e.cautions)]
        remarks = "".join(f"<span class=\"pill\">{_esc(p)}</span>" for p in pills) + _esc("; ".join(e.notes))
        sign = "up" if e.effect == "facilitation" else "down" if e.effect == "inhibition" else ""
        rows.append(f"<tr><td>{_esc(net.nodes[e.source].name or e.source)}</td>"
                    f"<td>{_esc(net.nodes[e.target].name or e.target)}</td>"
                    f"<td class=\"{sign}\">{_esc(_direction(e))}</td>"
                    f"<td class=\"nowrap\">{_mean_sd(e.strength, e.sd)}</td>"
                    f"<td>{_number(e.effect_over_sd, '.2f', MISSING)}</td>"
                    f"<td>{_esc(_number(e.n_with, 'd'))} / {_esc(_number(e.n_without, 'd'))}</td>"
                    f"<td>{_number(e.q_value, '.3g', MISSING)}</td><td>{_esc(e.condition)}</td>"
                    f"<td>{remarks}</td><td>{_esc(' '.join(e.study_ids))}</td></tr>")
    return "".join(rows)


def _hidden_note(hidden: dict) -> str:
    n = hidden.get("low_quality", 0)
    note = "" if not n else (f"<p class=\"muted\">Hidden by default: {n} low-quality edge(s). Tick them in "
                             "Advanced settings to show them.</p>")
    if hidden.get("not_significant"):
        note += (f"<p class=\"muted\">Left out by the q-value filter: {hidden['not_significant']} "
                 "interaction(s) whose q-value is above the threshold. Untick it in Advanced settings "
                 "to see them.</p>")
    return note


def _mean_sd(mean, sd) -> str:
    if mean is None:
        # obligate and abolished arcs have no ratio by construction, which is a result, not a gap
        return "<span class=\"muted\" title=\"one side did not grow, so there is no ratio\">no ratio</span>"
    return f"{mean:+.2f}" + ("" if sd is None else f" &plusmn; {sd:.2f}")


def _absent_section(result: dict, absence: dict) -> str:
    """Arcs below the absence threshold, reported here whether or not a file holds them."""
    in_file = [e for e in result["network"].edges if e.status == "absent"]
    left_out = result.get("absent")
    net = result["network"] if in_file else left_out
    absent = in_file or (list(left_out.edges) if left_out else [])
    if not absent:
        return ""
    k = absence.get("k", ABSENCE_THRESHOLD)
    where = ("Kept in the downloads with status absent; the Cytoscape style hides them by default."
             if in_file else "Left out of the downloads and of Cytoscape, so every count agrees with this "
             "page; tick Include arcs below the absence threshold to keep them.")
    return (f"<details><summary>{len(absent)} edge(s) below the absence threshold (k = {k:g})</summary>"
            f"<p class=\"muted\">|log2 mean| &lt; {k:g} &times; sd: no interaction at this threshold. {where}</p>"
            f"<div class=\"scroll\"><table>{HEADER}{_arc_rows(net, absent)}</table></div></details>")


def _sources(net) -> str:
    """Every study behind the table, with its citation and license: attribution at the edge level."""
    if not net.studies:
        return ""
    by_study = studies_with_edges(net)
    items = "".join(
        f"<li>{_esc(sid)}: {_esc(study.citation or sid)} "
        f"[{_esc(study.license or 'license: see study')}] supports {len(by_study.get(sid, []))} "
        f"interaction(s)" + (f" &middot; <a href=\"{_esc(study.url)}\">study</a>" if study.url else "") + "</li>"
        for sid, study in sorted(net.studies.items()))
    return ("<h2>Sources</h2><p class=\"muted\">Cited at the level of each interaction; per-study licenses "
            f"are respected.</p><ul class=\"sources\">{items}</ul>")


def _outputs(token: str, result: dict, has_edges: bool) -> str:
    """The outputs Karoline asked for: the network with a format menu, Cytoscape, the report (#76), and,
    when the search reported growth rates, the rates and the gLV parameters (#108)."""
    t = _esc(token)
    # every output names the search it belongs to, so two tabs never mix their networks up
    job = _esc(result.get("job", ""))
    tail = f"&amp;job={job}" if job else ""
    download = (f"<form class=\"inline\" method=\"get\" action=\"/download\">"
                f"<input type=\"hidden\" name=\"token\" value=\"{t}\">"
                + (f"<input type=\"hidden\" name=\"job\" value=\"{job}\">" if job else "") +
                "<button class=\"primary\" type=\"submit\">Download network</button> "
                "<select name=\"format\" aria-label=\"Network format\">"
                "<option value=\"json\">JSON</option><option value=\"graphml\">GraphML</option>"
                "<option value=\"matrix\">Adjacency matrix (CSV)</option>"
                "<option value=\"matrix_about\">Adjacency matrix: what it is (TXT)</option></select></form>")
    cytoscape = (f"<form class=\"inline\" method=\"post\" action=\"/cytoscape?token={t}{tail}\">"
                 "<button type=\"submit\">Send to Cytoscape</button></form>")
    report = (f"<details class=\"report\"><summary class=\"btn\">Report</summary>"
              f"<pre>{_esc(report_text(result))}</pre>"
              f"<p><a class=\"btn\" href=\"/report.txt?token={t}{tail}\">Download the report (.txt)</a></p></details>")
    organism_rates = result.get("rates") or {}
    rates_file = (f"<a class=\"btn\" href=\"/rates.csv?token={t}{tail}\">Download the growth rates (.csv)</a>"
                  if organism_rates else "")
    # the gLV parameters need a growth rate per organism, so the button appears with the rates (Karoline,
    # 2026-10-03: "another extra button to generate gLV parameters from the current run (when 'Report growth
    # rates' was enabled)")
    # one control with a menu, not two buttons (Karoline, 2026-10-03: "one single drop-down menu for gLV
    # results where the user chooses whether to download or to send to R")
    glv = (f"<form class=\"inline\" method=\"post\" action=\"/glv?token={t}{tail}\">"
           "<button type=\"submit\">Get gLV parameters</button> "
           "<select name=\"to\" aria-label=\"What to do with the gLV parameters\">"
           "<option value=\"zip\">Download (.zip)</option>"
           "<option value=\"r\">Send to R</option></select></form>"
           if organism_rates and has_edges else "")
    count = matrix.counts(result["network"])
    # a cell cannot say that it holds no number because one side did not grow, so the page says it here,
    # beside the download that writes those cells (#129, settled by Karoline 2026-10-08)
    na = matrix.bounded_cells(result["network"])
    na_hint = ""
    if na:
        named = "; ".join(f"{actor} on {affected}"
                          + ("" if size is None else f" (at {'least' if size > 0 else 'most'} log2 "
                                                     f"{size:+.4g})")
                          for affected, actor, size in na[:6])
        more = "" if len(na) <= 6 else f", and {len(na) - 6} more"
        na_hint = (f" {len(na)} cell(s) hold <code>NA</code> rather than a number, because one side did not "
                   f"grow at all and no ratio exists: {named}{more}. The arc carries the measured bound the "
                   "no-growth rule puts on that side, and the report prints it with its rule.")
    hint = ("<p class=\"hint\">Send to Cytoscape needs Cytoscape running on this machine; the network arrives in "
            "the legend's style. The report holds every setting and every reason a pair gave no edge. The "
            f"adjacency matrix holds one cell per ordered pair, so this search's {count['arcs']} arc(s) that "
            f"reach it make {count['cells']} cell(s) over {count['organisms']} organism(s): arcs of one pair "
            f"from different conditions or studies merge by their median."
            # a within-genus arc has no cell of its own, because the diagonal is written there; saying so
            # is what stops the two counts disagreeing silently (#248)
            + (f" {count['within_one_organism']} arc(s) are from one organism to itself, which "
               "--merge-genera produces, and have no cell in this matrix: the diagonal is written there."
               if count.get("within_one_organism") else "")
            + f"{na_hint}</p>")
    rate_hint = ("<p class=\"hint\">The growth rates are each organism's maximum specific growth rate in "
                 "monoculture, the median over the replicates and studies that have one, with the lag and the "
                 "carrying capacity beside each. The gLV package holds fitted per-capita coefficients, one "
                 "matrix per abundance unit, the matching growth rates and a README stating every formula "
                 "and naming whatever could not be fitted.</p>") if organism_rates else ""
    units = matrix.abundance_units(result["network"], organism_rates)
    # nothing is converted between abundance units, so a search spanning several writes several matrices,
    # and the page says so before the download rather than only in the package (Karoline, 2026-10-06)
    unit_hint = (f"<p class=\"hint\">These organisms are counted in {len(units)} abundance units "
                 f"({_esc(', '.join(units))}), so the package will hold {len(units)} matrices, one per "
                 "unit: a cell is per-capita, in 1/(time x abundance), and nothing is converted between "
                 "units because a cell mass conversion would have to be invented. No effect between them "
                 "was measured either, since organisms counted differently were never grown together, so "
                 "they are separate systems rather than one matrix with corners missing.</p>"
                 if len(units) > 1 else "")
    r_hint = (f"<p class=\"hint\">Send to R needs an R session waiting for it: install the companion package "
              f"once with <code>{_esc(rbridge.INSTALL_R)}</code> (if that answers 404, see the help), then run "
              f"<code>library(grownet); glv &lt;- grownet_listen()</code> and "
              f"press this. What arrives prints its own caveats, names every cell from a comparison where "
              f"one side did not grow, "
              f"and refuses to build a simulation for an organism with no growth rate "
              f"(<a href=\"/help?token={t}{tail}#glv\">the help explains it</a>). Without a listener, read the "
              f"same parameters in R with <code>glv &lt;- grownet_glv(&quot;{_esc(_glv_url(token, result))}"
              f"&quot;)</code>.</p>") if organism_rates and has_edges else ""
    missing_rate = _without_a_rate(result)
    return (f"<div class=\"bar outputs\">{download if has_edges else ''}{cytoscape if has_edges else ''}"
            f"{report}{rates_file}{glv}</div>{hint if has_edges else ''}{rate_hint}{unit_hint}{r_hint}"
            f"{missing_rate}")


def _glv_url(token: str, result: dict) -> str:
    """The address the R package fetches the same parameters from, with the session token, so a user who
    cannot open a port is not stuck (`grownet.rbridge.unreachable` says the same)."""
    port = result.get("port") or ""
    job = result.get("job", "")
    return (f"http://127.0.0.1:{port}/glv.json?token={token}" + (f"&job={job}" if job else "")) if port else ""


def _without_a_rate(result: dict) -> str:
    """The organisms of the network that have no growth rate, said on the page, since a gLV simulation
    needs a rate for each of them from elsewhere."""
    missing = (result["network"].meta.get("growth_rates") or {}).get("without_a_rate") or []
    if not missing:
        return ""
    shown = ", ".join(_esc(name) for name in missing[:6])
    more = f" and {len(missing) - 6} more" if len(missing) > 6 else ""
    return (f"<p class=\"hint\">No monoculture growth rate for {shown}{more}: no batch monoculture of it was "
            "read, or its curves gave no rate. A gLV simulation needs a rate for each of them from elsewhere; "
            "the report says why each one has none.</p>")


def _unresolved_list(result: dict) -> str:
    """Every entry that gave nothing, with why and what mGrowthDB holds that may have been meant."""
    if not result["unresolved"]:
        return ""
    items = []
    for entry in result["unresolved"]:
        reason = result.get("reasons", {}).get(entry, "not in mGrowthDB")
        hints = result.get("suggestions", {}).get(entry)
        hint = f" Did you mean: {_esc(', '.join(hints))}?" if hints else ""
        items.append(f"<li><strong>{_esc(entry)}</strong>: {_esc(reason)}.{hint}</li>")
    return f"<p class=\"note\">Not used:</p><ul class=\"unresolved\">{''.join(items)}</ul>"


def _empty_reason(result: dict) -> str:
    """Why a search came back empty, with what the second box left out said first (#113)."""
    reason = _empty_reason_core(result)
    s = result.get("settings", {})
    # the integrated form fits a row from a time course, so a sparsely sampled study gives it nothing
    # where the specified comparison needs only two measurements per set. Say which setting moves, as the
    # page does everywhere else. It is gLV mode that selects that form (2026-10-10), so this is what a
    # reader meets when a package comes out empty rather than on an ordinary search.
    if s.get("derivation", DEFAULTS["derivation"]) == "integrated" and any(
            "too few to fit a row" in why or "usable time point" in why
            for _, why in result.get("skipped", ())):
        reason += (" These curves are too sparsely sampled for the integrated derivation, which gLV mode "
                   "selects and which fits each organism's row from its whole time course. The default "
                   "comparison of replicate sets needs only two measurements per set: press gLV mode "
                   "again, or set Derivation to replicate in Advanced settings.")
    unmatched = len([r for _, r in result.get("skipped", ()) if "no experiment of this study matches" in r])
    if s.get("conditions") and unmatched and "second box" not in reason:
        studies = len(result.get("studies", ()))
        reason = (f"The second box left out {unmatched} of the {studies} study(ies) searched: no experiment "
                  f"there matches {_esc(s['conditions'])}. " + reason)
    return reason + _settings_to_try(s)


# the controls that can take a network to zero on their own, in the order worth checking, with what to
# try. Several of these did it in silence while the page blamed mGrowthDB's replicate structure and never
# named the setting: `min_studies 2` removes every arc when nothing is merged, `spike_factor 1` empties
# the network although the help warns only about 0, and `rate_window 1` empties it with a perfectly
# worded reason that reached the per-pair skip list and was then hidden (#220).
_EMPTYING = (
    ("min_studies", "Arcs from at least N studies", "it counts the studies behind a MERGED arc, so with "
     "nothing merged every arc counts as 1 and all of them are removed: tick Merge arcs, or set it to 1"),
    ("spike_factor", "Spike limit", "a low limit drops replicates as spiked, and 1 drops almost all of "
     "them: raise it, or set it to 0 to switch the check off"),
    ("rate_window", "Growth rate window", "the rate is a line fitted over this many points, so a small "
     "window gives no rate and the pairs that needed one are left out"),
    ("absence_threshold", "Absence threshold", "a high threshold calls every arc absent: lower it, or "
     "tick Include arcs below the absence threshold to see them"),
    ("max_adjusted_p", "Maximum adjusted p", "a strict q-value filter can remove every arc: the hidden "
     "count above says how many it took"),
    ("no_growth_factor", "No-growth rise factor", "a high factor calls every set no-growth"),
)


def _settings_to_try(s: dict) -> str:
    """The settings that are not at their defaults, named, when a search came back empty.

    The page's own notes blamed the species filter, then said "the species do not affect each other by
    that rule", then blamed mGrowthDB's replicate structure, while a control the reader had changed was
    discarding measured arcs and was never named (#220). This does not guess which one did it; it says
    which ones could and what to try, which is what a person needs to get unstuck.
    """
    changed = []
    for key, label, hint in _EMPTYING:
        if key not in s or key not in DEFAULTS:
            continue
        if s[key] != DEFAULTS[key]:
            changed.append(f"{label} is {s[key]}, not {DEFAULTS[key]}: {hint}")
    if not changed:
        return ""
    return (" <strong>Settings you changed that can empty a network on their own:</strong> "
            + "; ".join(changed) + ".")


def _empty_reason_core(result: dict) -> str:
    """Why a search came back empty: the first step, or the setting, that left nothing."""
    s = result.get("settings", {})
    if result.get("all") and not result["studies"]:
        return "Every study is in Exclude these studies, or mGrowthDB returned no study; empty that setting."
    if not result["resolved"] and not result.get("all"):
        return "None of the entries could be used; each one says why above."
    if result.get("errors"):
        # FETCH failures only. `errors` used to hold nothing else, and then advisory messages were added
        # to it (a mistyped id in Exclude these studies, a steady-state check asked for without growth
        # rates), so an empty network caused by the reader's own setting was reported as "mGrowthDB could
        # not be read" in a run where mGrowthDB answered every request: the lead sentence did the exact
        # thing #220 and #243 exist to stop. Advisory messages travel in `notes` now.
        return "mGrowthDB could not be read (see the messages above); try again when it is reachable."
    if not result["studies"]:
        if result.get("excluded"):
            return ("The only studies holding these species are in Exclude these studies ("
                    + _esc(", ".join(result["excluded"])) + "); remove them from that setting to search them.")
        if s.get("conditions"):
            return ("None of the studies in the second box (media, experiments or studies) holds these "
                    "species; empty that box or name another study.")
        return "mGrowthDB holds these strains, but no study grows them, so there is nothing to compare."
    if result.get("partners_only"):
        return (f"Everything these studies hold for your species involves a species you did not enter "
                f"({result['partners_only']} co-culture(s) or interaction(s)). Add the partners, or untick Only "
                "interactions between the species entered.")
    if result.get("hidden", {}).get("not_significant"):
        return (f"The q-value filter left out all {result['hidden']['not_significant']} interaction(s) "
                "found: none has a q-value at or below its threshold. Untick it in Advanced settings "
                "to see them.")
    if result.get("hidden", {}).get("low_quality"):
        return (f"{result['hidden']['low_quality']} low-quality interaction(s) were found and are hidden; tick "
                "Show low-quality edges to see them.")
    if result.get("hidden", {}).get("absent"):
        # the comparisons ran and none reached the threshold: say that, not that the data could not be used
        k = result.get("absence", {}).get("k", ABSENCE_THRESHOLD)
        return (f"All {result['hidden']['absent']} comparison(s) came out below the absence threshold "
                f"(k = {k:g}): the species do not affect each other by that rule. They are listed below, "
                "and a lower k or Include arcs below the absence threshold keeps them in the file.")
    reasons = [reason for _, reason in result["skipped"]]
    unmatched = [r for r in reasons if "no experiment of this study matches" in r]
    if unmatched and len(unmatched) == len(result["studies"]):
        # the second box named a medium or an id that nothing in these studies carries (#113)
        return ("No experiment of the studies holding these species matches the second box ("
                + _esc(s.get("conditions", "")) + "). A medium is matched as text, so a shorter word finds "
                "more spellings; the report lists every study it looked at.")
    only_monocultures = [r for r in reasons if r.startswith("only monocultures")]
    if only_monocultures and len(only_monocultures) == len(result["studies"]):
        return ("The studies holding these species grew them only alone, in monocultures, so there is no "
                "co-culture or community to compare with.")
    non_batch = [r for r in reasons if "excluded by default with the growth measure" in r]
    if non_batch and len(non_batch) == len(reasons) and not s.get("include_non_batch"):
        return ("These studies are chemostat or serial dilution experiments. Their area under the curve and "
                "growth rate are not comparable with a batch run, so they are left out; set the growth "
                "measure to max, which that mode suits, or tick Include chemostat and serial dilution "
                "experiments.")
    top = Counter(r.split(";")[0].strip() for r in reasons).most_common(1)
    why = f" The most common reason: {_esc(top[0][0])}." if top else ""
    return (f"The studies holding these species gave no usable comparison.{why} {EMPTY_HELP} The report lists "
            "the reason for every pair.")


def _result_section(token: str, result: dict, message: str = "") -> str:
    genera = result.get("genera", {})

    def entry_line(entry, matches):
        strains = ", ".join(f"{name} ({tid})" for tid, name in sorted(matches.items()))
        if entry in genera:                      # a genus entered alone: its species, then its strains
            return (f"<li>{_esc(entry)} (genus): {_esc(', '.join(genera[entry]))}"
                    f"<br><span class=\"muted\">{len(matches)} strain(s): {_esc(strains)}</span></li>")
        return f"<li>{_esc(entry)}: {_esc(strains)}</li>"

    resolved = "".join(entry_line(entry, matches) for entry, matches in result["resolved"])
    species_heading = "<h2>Species</h2>"
    if result.get("all"):
        daily_note = (f" (the network derived once a day, on {_esc(result['published'][:16].replace('T', ' '))}; "
                      "any other setting derives it live)" if result.get("published") else "")
        # "All of mGrowthDB" is only true when the second box is empty. All keeps reading that box and
        # Exclude these studies, which is deliberate (see run_query's docstring, Karoline 2026-09-28), so
        # the heading has to say which it was: the gLV example button fills that box and leaves it filled,
        # so pressing gLV example and then All gave a two-arc network of one study under a heading saying
        # the whole database (#193).
        # BOTH controls, which this comment named and the first version read only the first of: a study
        # left in Exclude these studies narrows All just as the second box does, and the page said
        # "All of mGrowthDB" over "every study, with every partner: 0 studies" (found reviewing #242).
        settings_here = result.get("settings", {})
        narrowed = [line for line in (settings_here.get("conditions") or "").splitlines() if line.strip()]
        excluded_ids = [x.strip() for x in (settings_here.get("exclude_studies") or "").split(",")
                        if x.strip()]
        if narrowed or excluded_ids:
            which = ("the second box" if narrowed and not excluded_ids
                     else "Exclude these studies" if excluded_ids and not narrowed
                     else "the second box and Exclude these studies")
            species_heading = f"<h2>All, narrowed by {which}</h2>"
            parts = []
            if narrowed:
                shown_filter = ", ".join(_esc(x.strip()) for x in narrowed[:3])
                more = f" and {len(narrowed) - 3} more" if len(narrowed) > 3 else ""
                parts.append(f"matching {shown_filter}{more}")
            if excluded_ids:
                parts.append("excluding " + ", ".join(_esc(x) for x in excluded_ids[:3])
                             + (f" and {len(excluded_ids) - 3} more" if len(excluded_ids) > 3 else ""))
            resolved = (f"<li>every study {' and '.join(parts)}, with every partner: "
                        f"{len(result['studies'])} studies{daily_note}</li>"
                        "<li class=\"muted\">All ignores the species box, not these. Clear them to derive "
                        "the whole of mGrowthDB.</li>")
        else:
            species_heading, resolved = "<h2>All of mGrowthDB</h2>", (
                f"<li>every study, with every partner: {len(result['studies'])} studies{daily_note}</li>")
    unresolved = _unresolved_list(result)
    net = result["network"]
    mismatch = any("MISMATCH" in (e.method or "") for e in net.edges)
    hidden = _hidden_note(result.get("hidden", {}))
    shown = [e for e in net.edges if e.status != "absent"]
    note = f"<p class=\"note\">{_esc(message)}</p>" if message else ""
    outputs = _outputs(token, result, bool(net.edges))
    if shown:
        table = (f"<h2>{len(shown)} interaction(s)</h2>{outputs}"
                 f"<p class=\"note\">{_esc(net.meta.get('provisional', PROVISIONAL))}"
                 + (f" {MISMATCH}" if mismatch else "") + "</p>"
                 f"{hidden}<div class=\"scroll\"><table>{HEADER}{_arc_rows(net, shown)}</table></div>")
    elif net.edges:
        filtered = result.get("hidden", {}).get("not_significant")
        heading = ("No interactions pass the q-value filter" if filtered
                   else "No interactions above the absence threshold")
        table = (f"<h2>{heading}</h2>{outputs}"
                 f"<p class=\"note\">{_esc(net.meta.get('provisional', PROVISIONAL))}</p>{hidden}")
    else:
        # an arc the threshold or the filter removed is no longer in the network (Karoline, 2026-10-03), so
        # an empty result says which rule emptied it, and the caution says what that rule does
        why = net.meta.get("provisional", PROVISIONAL) if result.get("hidden", {}).get("not_significant") else ""
        table = (f"<h2>No interactions</h2><p class=\"note\">{_empty_reason(result)} "
                 f"<a href=\"/help?token={_esc(token)}{_esc(_job_suffix(result.get('job', '')))}#empty\">What to "
                 f"try</a>.</p>" + (f"<p class=\"note\">{_esc(why)}</p>" if why else "")
                 + f"{hidden}{outputs}")
    studies = ", ".join(result["studies"]) or "none"
    skipped = ""
    skips = condensed(result["skipped"])
    if skips:
        # two kinds, and counting them together said a condition was a pair that gave no edge while an
        # arc derived from that condition was reported above it (#232). The cut at 50 was also silent:
        # the summary printed the full count and the list showed 50 of it.
        groups = [("pair(s) the data did not support",
                   [s for s in skips if about_a_pair(*s)]),
                  ("note(s) on the data read, which are not pairs",
                   [s for s in skips if not about_a_pair(*s)])]
        blocks = []
        for heading, entries in groups:
            if not entries:
                continue
            items = "".join(f"<li>{_esc(label)}: {_esc(reason)}</li>" for label, reason in entries[:50])
            more = (f"<li class=\"muted\">showing 50 of {len(entries)}; the report below holds them all"
                    "</li>" if len(entries) > 50 else "")
            blocks.append(f"<details><summary>{len(entries)} {heading}</summary>"
                          f"<ul>{items}{more}</ul></details>")
        skipped = "".join(blocks)
    errors = "".join(f"<p class=\"note\">{_esc(e)}</p>"
                     for e in [*result["errors"], *result.get("notes", ())])
    # and one line naming the settings that are not at their defaults, on EVERY result and not only an
    # empty one: a run that returns arcs under a changed threshold is the case a reader most needs told,
    # and it was the one case the page did not mark (#250)
    from .help import SETTINGS as help_settings
    s_here = result.get("settings", {})
    off_default = [k for k, v in s_here.items() if k in DEFAULTS and v != DEFAULTS[k]]
    if off_default:
        named = ", ".join(f"{_esc(help_settings[k][0] if k in help_settings else k)} = {_esc(str(s_here[k]))}"
                          for k in sorted(off_default)[:6])
        more = f", and {len(off_default) - 6} more" if len(off_default) > 6 else ""
        errors += (f"<p class=\"muted\">{len(off_default)} setting(s) are not at their default: "
                   f"{named}{more}. Advanced settings is open below.</p>")
    # and the settings this DERIVATION does not read, which is a different thing from a changed one: a
    # reader who sees "Include drop-out communities: on" beside a form that derives none has been told
    # something false about their own run (#215 item 3)
    unused = [k for k in (getattr(net, "meta", {}) or {}).get("settings_not_used") or () if k in s_here]
    if unused:
        told = ", ".join(_esc(help_settings[k][0] if k in help_settings else k) for k in sorted(unused))
        errors += (f"<p class=\"muted\">{len(unused)} setting(s) are recorded but NOT read by the "
                   f"{_esc(s_here.get('derivation', ''))} derivation, so changing them changes nothing "
                   f"here: {told}.</p>")
    return (f"<section class=\"result\" id=\"result\">{note}{species_heading}<ul>{resolved}</ul>{unresolved}"
            f"<p class=\"muted\">Studies searched: {_esc(studies)}</p>{errors}{table}"
            f"{_absent_section(result, result.get('absence', {}))}{_sources(net)}{skipped}</section>")


def render_result(token: str, result: dict, message: str = "") -> str:
    """The page with the result under the settings that produced it (#74)."""
    settings = result.get("settings") or {}
    return render_form(token, "\n".join(result.get("entries", [])), settings,
                       below=_result_section(token, result, message), job=result.get("job", ""),
                       conditions=settings.get("conditions", ""))


def _no_growth(s: dict, which: str) -> float:
    """A no-growth setting as the form shows it: the value chosen, or the rule's default."""
    value = s.get(f"no_growth_{which}")
    return value if value is not None else getattr(interaction, f"NO_GROWTH_{which.upper()}")


# What the page says when the mode is switched on and off.
GLV_MODE_MESSAGE = ("gLV mode on: growth rates on, drop-out communities off, the comparison on the "
                    "growth rate, and the derivation on the integrated form, which is what a fitted "
                    "coefficient is made of. All four are in Advanced settings, and pressing gLV mode "
                    "again switches them back. Name one medium in the second box to keep a simulation "
                    "to one environment.")
GLV_MODE_OFF_MESSAGE = ("gLV mode off: growth rates off, drop-out communities included again, the "
                        "comparison back on the area under the curve and the derivation back to the "
                        "comparison of replicate sets, which are the defaults.")


def chosen_deriver(settings: dict, client=None):
    """The derivation a search runs, or None for the specified comparison, which `derive_interactions`
    builds itself. The integrated form of #127 is the advanced alternative Karoline approved."""
    if (settings or {}).get("derivation") != "integrated":
        return None
    from .integrated import IntegratedDeriver
    return IntegratedDeriver(client=client, spike_factor=settings.get("spike_factor"),
                             include_non_batch=settings.get("include_non_batch", False))


def glv_mode_on(settings: dict) -> bool:
    """Whether the settings are the ones gLV mode sets.

    Every setting `glv_mode` writes is read here. It read three while the mode wrote four, so the toggle
    said "on" with the comparison selected, which is the one state in which a coefficient is NOT being
    fitted by the form the mode exists to select, and pressing it then switched the mode off instead of
    completing it (found reviewing #199, 2026-10-10).
    """
    s = {**DEFAULTS, **(settings or {})}
    return (bool(s["report_rates"]) and not s["include_dropout"] and s["metric"] == "growth_rate"
            and s["derivation"] == "integrated")


def glv_mode(settings: dict, on: bool = True) -> dict:
    """The settings a gLV simulation needs: a growth rate per organism, and no arc that may act through a
    third species (Karoline, 2026-10-04). `on` False puts both back to their defaults, since the button
    toggles ("Do I click a 2nd time to switch it off?").
    """
    if on:
        # the coefficients of #119 need the comparison to be on a GROWTH RATE, which auc and max cannot
        # produce. The rate method is left alone: easylinear by default, since Karoline chose it on
        # 2026-10-06 ("easylinear since it works better"), with the lag still Baranyi's, and anyone who
        # wants Baranyi rates sets it in Advanced settings.
        # and the integrated form, which is what a coefficient should be fitted by: it fits the row from
        # the whole time course rather than dividing a difference of two rates by one partner mean
        # (Karoline, 2026-10-10)
        return {**settings, "report_rates": True, "include_dropout": False, "metric": "growth_rate",
                "derivation": "integrated"}
    return {**settings, "report_rates": DEFAULTS["report_rates"],
            "include_dropout": DEFAULTS["include_dropout"], "metric": DEFAULTS["metric"],
            "derivation": DEFAULTS["derivation"]}


def _finite(form: dict, key: str) -> float | None:
    """The absolute value of a finite number posted under `key`, or None when there is not one.

    `float()` accepts "nan", "inf" and "1e999". A non-finite setting was echoed back to the form as the
    value in force and copied into `meta.settings`, where `json.dumps` writes the bare tokens `NaN` and
    `Infinity`. RFC 8259 section 6 forbids both, so R and every other strict parser refuses the whole
    file, while grownet's own `validate` accepts it, because Python's json module reads the specials by
    default: nothing between the two caught it (#195). A non-finite number is also not a threshold any
    measurement can be compared against, so it falls back to the default like any other unreadable value.

    `max_adjusted_p` does not need this: it keeps its parsed value only when `0 < value <= 1`, which is
    False for both `nan` and `inf`, so it already falls back.
    """
    try:
        value = abs(float(form.get(key, [""])[0]))
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def parse_settings(form: dict) -> dict:
    """Settings from the posted form, falling back to the defaults for anything missing or unreadable."""
    settings = dict(DEFAULTS)
    metric = form.get("metric", [""])[0]
    if metric in METRICS:
        settings["metric"] = metric
    rate_method = form.get("rate_method", [""])[0]
    if rate_method in rates.METHODS:
        settings["rate_method"] = rate_method
    try:
        settings["rate_window"] = max(2, int(form.get("rate_window", [""])[0]))
    except ValueError:
        pass
    spike = _finite(form, "spike_factor")
    if spike is not None:
        settings["spike_factor"] = spike
    fall = _finite(form, "capacity_max_fall")
    if fall is not None:
        settings["capacity_max_fall"] = fall
    settings["include_low_quality"] = bool(form.get("include_low_quality"))
    settings["include_absent"] = bool(form.get("include_absent"))
    settings["include_dropout"] = bool(form.get("include_dropout"))
    settings["include_non_batch"] = bool(form.get("include_non_batch"))
    settings["merge_arcs"] = bool(form.get("merge_arcs"))
    settings["merge_genera"] = bool(form.get("merge_genera"))
    try:
        settings["min_studies"] = max(1, int(form.get("min_studies", [""])[0]))
    except ValueError:
        pass
    absent = _finite(form, "absence_threshold")
    if absent is not None:
        settings["absence_threshold"] = absent
    for key in ("no_growth_alpha", "no_growth_factor"):
        value = _finite(form, key)
        if value is not None:
            settings[key] = value
    settings["max_adjusted_p"] = None
    if form.get("filter_adjusted_p"):
        try:
            value = abs(float(form.get("max_adjusted_p", [""])[0]))
        except ValueError:
            value = ADJUSTED_P_DEFAULT
        settings["max_adjusted_p"] = value if 0 < value <= 1 else ADJUSTED_P_DEFAULT
    correction = form.get("correction", [""])[0]
    if correction in ("bh", "by"):
        settings["correction"] = correction
    settings["conditions"] = form.get("conditions", [""])[0].strip()
    settings["exclude_studies"] = form.get("exclude_studies", [""])[0].strip()
    settings["only_entered"] = bool(form.get("only_entered"))
    settings["report_rates"] = bool(form.get("report_rates"))
    settings["steady_check"] = bool(form.get("steady_check"))
    derivation = form.get("derivation", [""])[0]
    if derivation in DERIVATIONS:
        settings["derivation"] = derivation
    return settings


def _current_names(net, current: dict) -> None:
    """Name each strain node by its current name (#24): a study from before a reclassification may call
    taxon 411483 Faecalibacterium prausnitzii A2-165, the most recent one Faecalibacterium duncaniae
    A2-165. The genus and species key follows the name; the taxon id, which is the node's identity, stays.

    Only a node whose identity is its taxon id is renamed. A node keyed by name carries a taxon id that
    mGrowthDB gives to more than one species (SMGDB00000008: Lachnoclostridium clostridioforme and L.
    symbiosum both carry 1506553), so the id's latest name would be another species' name (found in the
    audit of 2026-09-28)."""
    for nid, node in list(net.nodes.items()):
        if node.identity != "ncbi":
            continue
        name = current.get(int(node.taxon_id)) if str(node.taxon_id or "").isdigit() else None
        if name and name != node.name:
            net.nodes[nid] = dataclasses.replace(node, name=name, species=genus_species(name))


def support_level(entries) -> str:
    """The pairs a genus arc counts (Karoline, 2026-09-28: at the level of the query): strain pairs when every
    entry is an NCBI taxon id, the only entry that picks one strain, and species pairs otherwise, since a
    name, even with a strain designation, resolves to every strain of its species."""
    ids = [e for e in entries if e.strip()]
    return "strain" if ids and all(TAXON_ID.match(e.strip()) for e in ids) else "species"


def run_query(client, entries, settings: dict | None = None, index: dict | None = None, progress=None,
              narrow: bool = True, all_studies: bool = False, published: bool = True) -> dict:
    """Species names or taxon ids to an interaction network, through mGrowthDB and the existing derivation.

    Returns {"resolved", "unresolved", "taxon_ids", "studies", "network", "skipped", "errors", "notes"}.
    Failures that concern one study are collected in "errors" instead of raising, so a single bad study
    does not
    lose the rest. `progress(done, total, message)`, when given, is told where the search is: `total` is
    None until the studies are known (#75).

    `all_studies` is the page's All button (Karoline, 2026-09-28): the entries are ignored and every study
    mGrowthDB holds is derived, with every partner kept, still under the second box (media, experiments or
    studies) and Exclude these studies. With the default settings it is read from the network derived once a
    day in the grownet repository when that is less than 36 hours old and was derived by the same derivation
    these settings ask for (`grownet.published`, #96); `published`
    False, or any other setting, derives it live.
    """
    def say(done, total, message):
        if progress:
            progress(done, total, message)

    s = {**DEFAULTS, **(settings or {})}
    if all_studies and published and daily.usable(s, DEFAULTS):
        say(0, None, "Reading today's All network from the grownet repository")
        why_live = []
        found = daily.fetch(s, why=why_live)   # only if derived the way this search would derive it
        if found:
            return found
    else:
        why_live = []
    names = [] if all_studies else split_entries(entries)    # one per line, and at commas and semicolons
    say(0, None, "Looking up the species in mGrowthDB")
    index = species_index(client) if index is None else index
    resolved = resolve_species(names, index)
    current = getattr(index, "current", {})
    # show each strain by its current name, the one its most recent study uses (#24)
    resolved["resolved"] = [(entry, {t: current.get(t, n) for t, n in matches.items()})
                            for entry, matches in resolved["resolved"]]
    # `errors` is FETCH failures and nothing else, because `_empty_reason_core` reads it as "mGrowthDB
    # could not be read". `notes` is everything advisory: a setting that could not act, a check that was
    # asked for and not run. Putting the second kind in the first made an empty network caused by the
    # reader's own setting read as a database failure, in a run where every request succeeded.
    errors, notes, skipped, records = [], [], [], []
    # why the network derived once a day was not served, when it was asked for: a stale file and a defect
    # in reading one looked the same before (#157)
    notes += [f"the network derived once a day in the grownet repository was not used, so All was derived "
              f"live: {reason}" for reason in why_live]

    # the second box: study ids in it narrow the search as "Only these studies" used to, media and
    # experiment ids are matched per experiment inside the derivation (#113)
    selection = selecting.parse(s["conditions"])
    studies = list(selection["studies"])
    if all_studies and not studies:
        studies = list(getattr(index, "studies", []))       # every study the species list was read from
    only_entered = s["only_entered"] and not all_studies
    if resolved["taxon_ids"] and not studies:
        # with media or experiment ids and no study id, every study holding the species is read and the
        # selection is applied to their experiments
        try:
            found = client.search(strain_ncbi_ids=",".join(str(t) for t in resolved["taxon_ids"]))
            studies = list(found.get("studies", []))
        except MGrowthDBError as e:
            errors.append(f"search failed: {e}")

    # studies the user excluded are never searched, whether found or named (Karoline, 2026-09-27)
    excluded = {sid.strip().upper() for sid in s["exclude_studies"].split(",") if sid.strip()}
    left_out = [sid for sid in studies if sid.upper() in excluded]
    studies = [sid for sid in studies if sid.upper() not in excluded]
    # an id that matched nothing was dropped in silence and recorded as applied, so a mistyped id
    # ("SMGDB0000002", one digit short) left the study in the search while the report said it was
    # excluded. The species box answers an unusable entry; this one said nothing (#221 item 2).
    searched = {sid.upper() for sid in [*studies, *left_out]}
    unused = sorted(sid for sid in excluded if sid not in searched)
    if unused:
        # `notes`, not `errors`: `_empty_reason_core` reads `errors` as "mGrowthDB could not be read",
        # so putting an advisory message there blamed the database for an empty network in a run where
        # every request succeeded, which is the thing this very change exists to stop
        notes.append("not used in Exclude these studies: " + ", ".join(unused)
                      + ". No study searched has that id, so nothing was excluded by it; a study id "
                      "looks like SMGDB00000002. The other ids in that setting were applied.")
    partners_only = 0                       # interactions dropped because a partner was not entered

    # A species name resolves to every strain of that species, and a strain keeps its taxon id across the
    # renamings mGrowthDB records (411483 is Faecalibacterium prausnitzii A2-165 in one study and
    # Faecalibacterium duncaniae A2-165 in others), so an edge is kept when either matches. Matching names
    # alone dropped every edge for a name the study does not use (#73).
    wanted = {genus_species(name) for _, matches in resolved["resolved"] for name in matches.values()}
    wanted_ids = {str(taxon) for taxon in resolved["taxon_ids"]}

    def keep(name, taxon):
        # a strain the search asked for: by taxon id, or by genus and species as the edge filter below
        return str(taxon) in wanted_ids or genus_species(name) in wanted

    # with "only the species entered", only what can give an interaction between them is read (identical
    # networks, checked against reading everything); read it all first, a few requests at a time
    narrowed = keep if (only_entered and narrow) else None
    # one instance for the whole search, so the network's statistics and the arcs come from the same
    # derivation rather than from a fresh object per study
    deriver = chosen_deriver(s, client)
    from .fetch import prefetch_studies
    prefetch_studies(client, studies, s["include_non_batch"], progress=lambda d, t, m: say(d, t, m),
                     # the default derivation refuses a community of three or more, so prefetching the
                     # drop-out designs reads curves nothing can use (#142 item 10)
                     keep=narrowed,
                     dropout=s["include_dropout"] and s["derivation"] != "integrated")
    unread_studies = []
    for i, study_id in enumerate(studies):
        say(i, len(studies), f"Reading {study_id} ({i + 1} of {len(studies)})")
        try:
            recs, skips = derive_interactions(client, study_id, deriver=deriver,
                                              metric=metric_name(s),
                                              spike_factor=s["spike_factor"], dropout=s["include_dropout"],
                                              include_non_batch=s["include_non_batch"],
                                              no_growth_alpha=s["no_growth_alpha"],
                                              no_growth_factor=s["no_growth_factor"], keep=narrowed,
                                              capacity_max_fall=s["capacity_max_fall"],
                                              selection=selection)
        except MGrowthDBError as e:
            errors.append(f"{study_id}: {e}")
            unread_studies.append(study_id)
            continue
        if only_entered:
            def entered(record, side):
                return (record.get(f"{side}_taxon_id") in wanted_ids
                        or record.get(f"{side}_species", record[side]) in wanted)

            kept = [r for r in recs if entered(r, "source") and entered(r, "target")]
            partners_only += len(recs) - len(kept)
            recs = kept
        records += recs
        skipped += skips
        # co-cultures left underived because their partner was not entered count like dropped interactions
        partners_only += sum("the partner is not among the species entered" in r for _, r in skips)

    # a request that failed after its retries leaves a gap in what was read, so the result is incomplete:
    # said at the top, not only among the pairs the data did not support (audit step 7, 2026-09-28)
    failed = unread(skipped)
    if failed:
        errors.append(f"{len(failed)} replicate(s) or growth curve(s) could not be read from mGrowthDB "
                      f"(for example {failed[0][0]}: {failed[0][1]}); the result is incomplete, so run the "
                      "search again")
    # the derivation that made these records says what it tests and what is provisional in it: the words
    # used to be the specified comparison's whatever had derived the network (#142 item 5)
    fitted_rows = list(records)
    kept, extra = output_meta(records, s["include_low_quality"], s["correction"], s["absence_threshold"],
                              s["no_growth_alpha"], s["no_growth_factor"], s["merge_arcs"], s["min_studies"],
                              s["merge_genera"], support_level(names), s["max_adjusted_p"],
                              s["include_absent"], deriver=deriver)
    # output_meta sets each record's status in place, so the arcs it left out below the threshold are still
    # here to show in their own section: the page reports them, the file holds what the page counts
    absent_records = [] if s["include_absent"] else [r for r in records if r.get("status") == ABSENT]
    # the organisms of the derived arcs, before any merge to the genus: a rate belongs to a strain, and the
    # monocultures of these organisms are the ones the search already read, so no rate costs a new request
    rate_nodes = {r[side] for r in records for side in ("source", "target")}
    records = kept
    # every setting the search ran with, so a downloaded network says how it was made (#78, #76)
    # `studies` in meta is the studies READ, as the schema says: a study that answered 404 was written
    # there as one of the sources, the run exited 0, and nothing in the file said anything failed (#247).
    # The failures travel in the file now, so a reader of the file alone can tell a complete run.
    read = [st for st in studies if st not in unread_studies]
    net = records_to_network(records, meta={
        "source_db": "mGrowthDB (live)", "query": "all" if all_studies else "species", "species": names,
        "studies": read, "settings": dict(s), "selection": selection, **extra})
    net.meta["errors"] = list(errors)
    net.meta["complete"] = not errors
    net.meta["data"] = data_versions(client, read, net.meta["derived_at"])
    _current_names(net, current)
    # the growth rates, when the page asked for them: each organism's maximum specific growth rate in
    # monoculture, median over replicates and studies (Karoline, 2026-10-03). They travel in the network's
    # meta, so a downloaded network carries the rates it was reported with.
    organism_rates = {}
    # from every row the derivation fitted, not the ones the display kept: the rate is a property of the
    # organism, and it moved by 14 per cent with --include-absent while it was a median over the arcs
    # that survived (Karoline, 2026-10-12, on #204: option 1)
    fitted = integrated.fitted_rates(fitted_rows) if s.get("derivation") == "integrated" else {}
    if fitted:
        # the derivation fitted a rate and a self-limitation per organism, and those are the parameters
        # that go with its coefficients (#127)
        organism_rates = {nid: entry for nid, entry in fitted.items() if nid in net.nodes}
        # named as the network names the node, so one organism carries one name in the report and the
        # files: the fitted rows still carried the name of the study they came from (#24)
        organism_rates = {nid: {**entry, "name": net.nodes[nid].name or entry.get("name", nid)}
                          for nid, entry in organism_rates.items()}
        # An organism whose fit implies no plateau is given the measured one inside `two_stage`, before
        # its partners are fitted against it, from the monocultures of its own condition (#142 item 7).
        # So there is no second pass here: it used to read every study's monocultures again to substitute
        # a plateau afterwards, which cost a crawl and published a row no fit had produced.
        # `self_limitation_source` on each row says where the diagonal came from, or why there is none.
        net.meta["growth_rates"] = matrix.rate_meta(net, organism_rates, integrated.METRIC)
    elif s["report_rates"]:
        say(len(studies), len(studies), "Reading the monoculture growth rates")
        found, rate_skips = growth_rates(client, studies, wanted=rate_nodes,
                                         rate_method=s["rate_method"], window=s["rate_window"],
                                         spike_factor=s["spike_factor"], progress=say,
                                         capacity_max_fall=s["capacity_max_fall"])
        organism_rates = matrix.for_nodes(net, found)
        skipped += rate_skips
        # a read that failed while the rates were read leaves the run incomplete as surely as one that
        # failed while the arcs were: the file was marked complete before this stage ran, so an organism
        # whose monocultures could not be read looked as if it had no measurable rate (#247)
        failed_rates = unread(rate_skips)
        if failed_rates:
            errors.append(f"{len(failed_rates)} replicate(s) or growth curve(s) could not be read from "
                          f"mGrowthDB while reading growth rates (for example {failed_rates[0][0]}: "
                          f"{failed_rates[0][1]}); the rates are incomplete, so run the search again")
            net.meta["errors"] = list(errors)
            net.meta["complete"] = False
        net.meta["growth_rates"] = matrix.rate_meta(
            net, organism_rates, rates.method_name(s["rate_method"], s["rate_window"]))
    # the steady-state check (#125): a chemostat satisfies A x = -(r - D) there, and those numbers were
    # never used to fit the parameters, so they test them. Off unless asked for: it reads the curves of
    # chemostats this search did not need.
    checked = None
    if s.get("steady_check") and not s.get("report_rates"):
        # The command line refuses this combination and names the remedy; the page used to tick the box,
        # run nothing, print "Check against chemostat steady states: on" in the report and write
        # `steady_check: true` into the downloaded network. One surface refusing what another drops in
        # silence is the defect, not which of the two is right (#233).
        notes.append("no steady-state check: it scores the growth rates and coefficients of the run, so "
                      "it needs Report growth rates, which gLV mode turns on. The setting is recorded as "
                      "asked for and nothing was scored.")
    elif s.get("steady_check") and organism_rates:
        say(len(studies), len(studies), "Reading the chemostat steady states")
        try:
            got = matrix.coefficients(net, organism_rates)
        except matrix.CannotConvert as e:
            notes.append(f"no steady-state check: {e}")
        else:
            checked = steady.check(got, organism_rates, steady.find(client, net, progress=say))
    elif s.get("steady_check"):
        # asked for, rates on, and no rate could be computed: say so rather than leaving the report's
        # "on" as the only trace
        notes.append("no steady-state check: no growth rate could be computed for this network, and the "
                      "check scores the rates and the coefficients the run produced.")
    say(len(studies), len(studies), "Preparing the result")
    # the arcs below the threshold, named as the network names them: the network's nodes are renamed to
    # their current names and these were not, so one organism appeared under two names in one report (#24)
    absent_net = records_to_network(absent_records) if absent_records else None
    if absent_net is not None:
        _current_names(absent_net, current)
    return {"entries": names, "settings": dict(s), "resolved": resolved["resolved"],
            "reasons": resolved["reasons"], "suggestions": resolved["suggestions"], "excluded": left_out,
            "all": all_studies, "genera": resolved["genera"],
            "partners_only": partners_only,
            "unresolved": resolved["unresolved"], "taxon_ids": resolved["taxon_ids"], "studies": studies,
            "network": net, "absent": absent_net,
            "rates": organism_rates, "steady": checked,
            "skipped": skipped, "errors": errors, "notes": notes,
            "hidden": extra["hidden"], "absence": extra["absence"]}


# searches kept for their pages, downloads and reports: the latest ones only, so a page left open all day
# does not keep every result in memory (code review of 2026-09-28)
GONE = "That search is no longer here; run it again."
RUNNING = "That search is still running; this will be ready when it finishes."
KEPT_JOBS = 20
# the species list (and All's list of studies) is read again after this many seconds, so a study published
# while the page runs is found without a restart (code review of 2026-09-28)
INDEX_MAX_AGE = 3600
_INDEX_LOCK = threading.Lock()
_RUNNING_LOCK = threading.Lock()


def reads_since(client, before: tuple, shared: bool) -> dict | None:
    """What one search read, as the difference of the client's counters over it, for the report (#187).

    The page keeps one client for an hour, whose counters also hold the species list and every earlier
    search, so the command line's way, handing `report_text` the client, would print the session's total
    as this search's. A search also fans out to worker threads, so the reads cannot be told apart by
    thread: when another search ran at the same time, `shared` says the difference holds both.
    None when the client keeps nothing, as on the command line, and then `before` is None too.

    The difference is sound only because a search's worker threads end with it: `fetch.prefetch_studies`
    uses `with ThreadPoolExecutor(...)`, which waits for every future on exit, so no read of this search
    lands in the next one's difference unflagged (checked by Craig's agent, on #283).
    """
    if before is None or not getattr(client, "cache_dir", None):
        return None
    (fetched, reused, remembered, refreshed), now = before, _counters(client)
    return {"fetched": now[0] - fetched, "reused": now[1] - reused, "remembered": now[2] - remembered,
            "refreshed": [sid for sid in now[3] if sid not in refreshed], "shared": shared}


def _counters(client) -> tuple:
    """(fetched, reused, remembered, refreshed) of a client that keeps a cache.

    Read directly, with no defaults: defaults made a real client missing a counter report "0 from
    mGrowthDB, 0 reused", the silence this line exists to end (Craig's agent, on #283). Only a client with
    a `cache_dir` reaches here, which every real client has and no test double defines.
    """
    return client.fetched, client.reused, client.remembered, list(client.refreshed)


def prune_jobs(jobs: dict, keep: int = KEPT_JOBS) -> None:
    """Drop all but the latest `keep` searches, never one still running (dicts keep insertion order)."""
    for old in list(jobs)[:-keep]:
        if jobs[old]["status"] != "running":
            del jobs[old]


class _Handler(http.server.BaseHTTPRequestHandler):
    """Routes: the page, a search and its progress, the downloads, the report and Cytoscape. Every request
    carries the session token."""

    token = ""
    client_factory = None
    state: dict = {}
    # a search that finishes within this many seconds shows its result at once, without the progress page
    wait = 1.0

    def log_message(self, *_args):
        pass                      # the browser is right there; no access log

    def _send(self, body, content_type: str = "text/html; charset=utf-8", filename: str = "",
              status: int = 200):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if filename:
            self.send_header("Content-Disposition", f"attachment; filename=\"{filename}\"")
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location: str):
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _authorized(self, query: dict) -> bool:
        """The session token, which is what keeps another program on this machine from driving the tool.

        Without it the answer is still 403, but it is grownet's own page saying what to do: opening
        http://127.0.0.1:PORT by hand, or an old tab from a previous run, used to show a bare server error
        (Karoline, 2026-10-04: "localhost:8791 shows an error"). The page never shows the token itself,
        since anything that could read it here could use it.
        """
        given = query.get("token", [""])[0]
        # compare BYTES: `secrets.compare_digest` raises TypeError on a str holding non-ASCII, and the
        # exception escaped, so the connection was closed with no status line at all and the browser
        # showed its own "site can't be reached". `secrets.token_urlsafe` emits "-" and "_", so any tool
        # that autocorrects a double hyphen to an en dash on the way to the reader produces exactly that,
        # and it failed worse than the case this function was written for (#246).
        if secrets.compare_digest(given.encode("utf-8", "surrogateescape"), self.token.encode("utf-8")):
            return True
        self._send(render_token_page(bool(given), self.server.server_address[1]), status=403)
        return False

    def _job_page(self, job_id: str) -> str:
        job = self.state.setdefault("jobs", {}).get(job_id)
        if job is None:
            return render_form(self.token, message="That search is no longer here; run it again.")
        if job["status"] == "running":
            return render_progress(self.token, job)
        if job["status"] == "failed":
            return render_form(self.token, "\n".join(job["entries"]), job["settings"], job["error"],
                               conditions=(job["settings"] or {}).get("conditions", ""))
        job["result"]["job"] = job["id"]
        job["result"]["port"] = self.server.server_address[1]
        self.state["result"] = job["result"]
        return render_result(self.token, job["result"])

    def _result(self, query: dict):
        """The search a request names with job=, or the latest one when it names none.

        **A request that names a search it cannot have is refused rather than answered with another
        one.** It used to fall through to the most recently viewed result, so a tab whose search had been
        pruned (`KEPT_JOBS`, after twenty more searches) downloaded somebody else's network under the
        ordinary filename, with HTTP 200 and nothing to say so, while the page for the same job id said
        plainly that the search was gone. Two tabs are enough to meet it (2026-10-10).
        """
        named = query.get("job", [""])[0]
        job = self.state.get("jobs", {}).get(named)
        if named and not (job and job.get("status") == "done"):
            return None
        result = job["result"] if job and job.get("status") == "done" else self.state.get("result")
        if result is not None:
            # the port this page is served from, so the result can print the address R fetches from
            result["port"] = self.server.server_address[1]
        return result

    def _gone(self, query: dict, otherwise: str) -> str:
        """Why there is nothing to give back: a search still running, one that is gone, or none run yet.

        A search that has not finished is refused for the same reason as one that is gone, since there is
        nothing to hand over either way, but it must not be told to run again: it is running, and saying
        so sends a reader to repeat work that is already under way (found reviewing #205, 2026-10-10).
        """
        named = query.get("job", [""])[0]
        if not named:
            return otherwise
        job = self.state.get("jobs", {}).get(named)
        return RUNNING if job and job.get("status") == "running" else GONE

    def _download(self, fmt: str, query: dict):
        result = self._result(query)
        if not result:
            self._send(render_form(self.token, message=self._gone(query, "Nothing to download yet.")))
        elif fmt == "graphml":
            self._send(to_graphml(result["network"]), "application/xml", f"{TITLE}_network.graphml")
        elif fmt == "matrix":
            # the adjacency matrix: the plain network as a square table, so its diagonal is 0; the gLV
            # package is where the diagonal is -1 (Karoline, 2026-10-03)
            self._send(matrix.matrix_csv(result["network"]), "text/csv; charset=utf-8",
                       f"{TITLE}_matrix.csv")
        elif fmt == "matrix_about":
            # what the grid is, which the CSV cannot carry without breaking a plain read.csv (#212)
            self._send(matrix.matrix_about(result["network"], f"{TITLE}_matrix.csv"),
                       "text/plain; charset=utf-8", matrix.about_name(f"{TITLE}_matrix.csv"))
        else:
            self._send(result["network"].to_json(), "application/json", f"{TITLE}_network.json")

    def do_GET(self):             # noqa: N802 - the name http.server requires
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if not self._authorized(query):
            return
        if parsed.path == "/":
            job = query.get("job", [""])[0]
            self._send(self._job_page(job) if job else render_form(self.token))
        elif parsed.path in ("/help", "/about", "/legend"):
            # the search these pages were opened from, so their Back returns to it; an id no longer kept
            # (or never given) gives the plain Back to a new search
            job = query.get("job", [""])[0]
            job = job if job in self.state.get("jobs", {}) else ""
            render = {"/help": render_help, "/about": render_about, "/legend": render_legend}[parsed.path]
            self._send(render(self.token, job))
        elif parsed.path == "/download":
            self._download(query.get("format", ["json"])[0], query)
        elif parsed.path in ("/download.json", "/download.graphml"):
            self._download(parsed.path.rsplit(".", 1)[1], query)
        elif parsed.path == "/download.matrix":
            self._download("matrix", query)
        elif parsed.path in ("/rates.csv", "/glv.zip", "/glv.json"):
            self._rates(parsed.path, query)
        elif parsed.path == "/grownet_style.xml":
            # the Cytoscape style as a file, the same as `grownet style` writes, so a downloaded GraphML can
            # take it without the command line (Karoline, 2026-09-28); XML, the one form Cytoscape imports
            self._send(style_xml(), "application/xml; charset=utf-8", "grownet_style.xml")
        elif parsed.path == "/report.txt":
            result = self._result(query)
            if not result:
                self._send(render_form(self.token,
                                       message=self._gone(query, "No report yet: run a search first.")))
            else:
                self._send(report_text(result), "text/plain; charset=utf-8", f"{TITLE}_report.txt")
        else:
            self.send_error(404, "no such page")

    def _rates(self, path: str, query: dict):
        """The growth rates on their own, and the gLV package: both need a search that reported rates."""
        result = self._result(query)
        if result is None:
            # `_gone` first, as `/download` and `/report.txt` already do: these four routes went straight
            # to "tick Report growth rates and run the search again" for a search that was STILL RUNNING
            # with that box already ticked, which is what `_gone`'s docstring says must not happen,
            # because it sends a reader to repeat work under way. These are the slow routes (#246).
            self._send(render_form(self.token, message=self._gone(
                query, "No growth rates yet: tick Report growth rates and run the search again.")))
            return
        organism_rates = result.get("rates") or {}
        if not organism_rates:
            self._send(render_form(self.token, message="No growth rates yet: tick Report growth rates and "
                                                       "run the search again."))
        elif path == "/rates.csv":
            self._send(matrix.rates_csv(organism_rates, result["network"]), "text/csv; charset=utf-8",
                       f"{TITLE}_growth_rates.csv")
        elif path == "/glv.json":
            # what the R package fetches, and what Send to R posts: the same numbers as the zip, with the
            # caveats as data and the README text (#110, converted on #120)
            payload = self._payload(result, organism_rates)
            if payload is not None:
                self._send(json.dumps(payload, indent=1), "application/json; charset=utf-8")
        else:
            self._package(result, organism_rates)

    def _payload(self, result, organism_rates):
        """The gLV payload, or None when the page has already said which setting to change (#119)."""
        try:
            return matrix.glv_payload(result["network"], organism_rates, self._extra(result))
        except matrix.CannotConvert as e:
            self._send(render_result(self.token, result, message=f"No gLV parameters: {e}"))
            return None

    def _extra(self, result) -> dict:
        """The files a package or a payload carries beside the numbers: the steady-state check (#125)."""
        return ({"steady_state_check.txt": steady.as_text(result["steady"])}
                if result.get("steady") is not None else {})

    def _package(self, result, organism_rates) -> None:
        """The zip, or the page saying which setting to change: a package of coefficients needs the
        comparison to be on a growth rate (#119)."""
        try:
            zipped = matrix.glv_package(result["network"], organism_rates, self._extra(result))
        except matrix.CannotConvert as e:
            self._send(render_result(self.token, result, message=f"No gLV package: {e}"))
            return
        self._send(zipped, "application/zip", f"{TITLE}_glv_parameters.zip")

    def _glv(self, query: dict, form: dict) -> None:
        """The page's one gLV control: the zip, or the parameters posted into a listening R session."""
        result = self._result(query)
        if result is None:                      # a running or pruned search, not a missing setting (#246)
            self._send(render_form(self.token, message=self._gone(
                query, "No gLV parameters yet: tick Report growth rates and run the search again.")))
            return
        organism_rates = result.get("rates") or {}
        if not organism_rates:
            self._send(render_form(self.token, message="No gLV parameters yet: tick Report growth rates "
                                                       "and run the search again."))
            return
        if form.get("to", ["zip"])[0] != "r":
            self._package(result, organism_rates)
            return
        payload = self._payload(result, organism_rates)
        if payload is None:
            return
        try:
            answer = rbridge.send(payload)
        except rbridge.RError as e:
            self._send(render_result(self.token, result, message=str(e)))
            return
        caveats = payload["caveats"]
        note = (f"Sent to R: {answer.get('organisms', 0)} organism(s), "
                f"{answer.get('growth_rates', 0)} growth rate(s), "
                f"{len(caveats['censored_cells'])} cell(s) from a comparison where one side did not "
                "grow. The R session printed what it holds "
                "and what to read before simulating.")
        self._send(render_result(self.token, result, message=note))

    def _to_cytoscape(self, query: dict) -> str:
        """Send the network already computed, without deriving it again (#25)."""
        result = self._result(query)
        if not result:
            return render_form(self.token, message=self._gone(query, "Nothing to send yet."))
        try:
            sent = send(result["network"], name=TITLE)
        except CytoscapeError as e:
            return render_result(self.token, result, message=str(e))
        if sent.get("warning"):
            return render_result(self.token, result, message=f"Sent to Cytoscape: network {sent['suid']}; "
                                 f"{sent['warning']}.")
        return render_result(self.token, result, message=f"Sent to Cytoscape: network {sent['suid']}, in the "
                             "grownet style (arcs as in the legend, nodes colored by genus).")

    def _start(self, entries: list, settings: dict, all_studies: bool = False) -> dict:
        """Run a search in a thread, so the page can show its progress while it runs (#75)."""
        job = {"id": secrets.token_hex(4), "status": "running", "done": 0, "total": None,
               "message": "Starting", "entries": [e.strip() for e in entries if e.strip()], "all": all_studies,
               "settings": settings, "result": None, "error": ""}

        def progress(done, total, message):
            job.update(done=done, total=total, message=message)

        def work():
            try:
                with _INDEX_LOCK:          # two first searches build it once, not twice
                    built = self.state.get("index_built", 0)
                    if self.state.get("index") is None or time.monotonic() - built > INDEX_MAX_AGE:
                        # the species list of all of mGrowthDB, and the client whose cache keeps what the
                        # searches read: both renewed once an hour, so a change in mGrowthDB is seen within
                        # the hour, and a second search does not read the same records again (audit of
                        # 2026-09-28: every search started with an empty cache)
                        fresh = self.client_factory()
                        progress(0, None, "Reading the species list of mGrowthDB (the first search in an hour)")
                        self.state["index"] = species_index(fresh, progress=progress)
                        self.state["client"] = fresh
                        self.state["index_built"] = time.monotonic()
                    client = self.state["client"]
                # any overlap marks both searches, since either one's difference then holds the other's reads
                with _RUNNING_LOCK:
                    running = self.state.setdefault("running", {})
                    for other in running.values():
                        other["overlapped"] = True
                    job["overlapped"] = bool(running)
                    running[job["id"]] = job
                before = _counters(client) if getattr(client, "cache_dir", None) else None
                try:
                    result = run_query(client, entries, settings, self.state["index"], progress=progress,
                                       all_studies=all_studies)
                finally:
                    with _RUNNING_LOCK:
                        running.pop(job["id"], None)
                result["reads"] = reads_since(client, before, job["overlapped"])
                job["result"] = result
                job["status"] = "done"
            except MGrowthDBError as e:
                job.update(status="failed", error=f"mGrowthDB is not reachable: {e}")
            except Exception as e:             # a bug must reach the page, not only a dead thread
                job.update(status="failed", error=f"The search failed: {type(e).__name__}: {e}")

        jobs = self.state.setdefault("jobs", {})
        jobs[job["id"]] = job
        prune_jobs(jobs)
        job["thread"] = threading.Thread(target=work, daemon=True)
        job["thread"].start()
        return job

    def do_POST(self):            # noqa: N802 - the name http.server requires
        parsed = urllib.parse.urlparse(self.path)
        if not self._authorized(urllib.parse.parse_qs(parsed.query)):
            return
        if parsed.path == "/cytoscape":
            self._send(self._to_cytoscape(urllib.parse.parse_qs(parsed.query)))
            return
        length = int(self.headers.get("Content-Length") or 0)
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
        if parsed.path == "/glv":
            self._glv(urllib.parse.parse_qs(parsed.query), form)
            return
        entries = form.get("species", [""])[0].splitlines()
        settings = parse_settings(form)
        if form.get("glv_mode"):
            # Karoline, 2026-10-04: a button "which will enable growth rate collection and disable drop-out
            # communities", and then: "Do I click a 2nd time to switch it off?" Yes. It sets or clears the
            # two settings, shows them in Advanced settings, and leaves the search for the user to start.
            turning_on = not glv_mode_on(settings)
            settings = glv_mode(settings, turning_on)
            self._send(render_form(self.token, "\n".join(entries), settings,
                                   message=GLV_MODE_MESSAGE if turning_on else GLV_MODE_OFF_MESSAGE,
                                   conditions=settings.get("conditions", "")))
            return
        if form.get("example"):
            # The Example shows what the tool does with nothing changed, so it puts every setting back to
            # its default rather than carrying the current ones through. It used to keep them, and the two
            # buttons beside it set some: after gLV mode the example ran with drop-out communities off,
            # and after the gLV example it ran with that example's study still in the second box. Either
            # gave an empty network with nothing on the page to say why (Karoline, 2026-10-09).
            self._send(render_form(self.token, "\n".join(EXAMPLE), dict(DEFAULTS),
                                   message=EXAMPLE_MESSAGE, conditions=""))
            return
        if form.get("glv_example"):
            # everything a working simulation needs, and then the search itself: the two organisms, the
            # study they are in so nothing else is read, and the whole of gLV mode. It used to add only
            # the growth rates and rely on the shipped derivation being the integrated form; with the
            # comparison back as the default it inherited that instead and the button produced a run no
            # package can be built from, on a study chosen for the other form (found reviewing #199,
            # 2026-10-10). It presses the mode rather than repeating parts of it, so the two cannot
            # drift again. The help's gLV section runs this package through miaSim step by step.
            # from the DEFAULTS, not from whatever the form posted: the Example button beside it was changed for
            # exactly this on 2026-10-09 ("It used to keep them... Either gave an empty network with
            # nothing on the page to say why", Karoline), and this one was left inheriting them, so
            # pressing it with an absence threshold of 9 still in the form filled the boxes, ran, and
            # produced no network and no package, against a caption promising a package that simulates
            settings = {**glv_mode(dict(DEFAULTS)), "conditions": GLV_EXAMPLE_STUDY}
            job = self._start(list(GLV_EXAMPLE), settings)
            job["thread"].join(self.wait)
            self._redirect(f"/?token={self.token}&job={job['id']}#result")
            return
        if form.get("all"):
            job = self._start([], settings, all_studies=True)
            job["thread"].join(self.wait)
            self._redirect(f"/?token={self.token}&job={job['id']}#result")
            return
        if not [e for e in entries if e.strip()]:
            self._send(render_form(self.token, settings=settings, message="Type at least one species.",
                                   conditions=settings.get("conditions", "")))
            return
        job = self._start(entries, settings)
        job["thread"].join(self.wait)
        self._redirect(f"/?token={self.token}&job={job['id']}#result")


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def serve(port: int = 0, open_browser: bool = True, client_factory=None) -> None:
    """Run the local page until interrupted. port 0 picks a free port."""
    from .mgrowthdb import MGrowthDBClient

    handler = type("CrossfeedHandler", (_Handler,), {
        "token": secrets.token_urlsafe(16),
        "client_factory": staticmethod(client_factory or MGrowthDBClient),
        "state": {},
    })
    try:
        server = _Server(("127.0.0.1", port), handler)
    except OSError as e:
        raise SystemExit(f"grownet gui: cannot use port {port} ({e.strerror}). Pick another with --port, "
                         "or leave it out to use a free one.") from None
    with server as httpd:
        url = f"http://127.0.0.1:{httpd.server_address[1]}/?token={handler.token}"
        print(f"{TITLE} is at {url}\nPress Ctrl+C to stop.", flush=True)
        if open_browser:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
