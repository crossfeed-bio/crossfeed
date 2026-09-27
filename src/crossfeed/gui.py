"""A local page: type species names, get their interaction network.

`crossfeed gui` starts a small server from the standard library on 127.0.0.1, with a random token in the
URL, and opens the browser. Nothing is hosted, nothing is uploaded, and the page has no JavaScript: the
form posts back and the server returns HTML rendered in Python. Settings live in an HTML `details` block
("Advanced settings"), so the plain page is a box for species and a button.

The work is in `run_query`, which is pure apart from the client it is given: names to taxon ids
(crossfeed.taxonomy), taxon ids to studies (mGrowthDB search), then the existing derivation per study.
Rendering is in `render_form` and `render_result`, so both are testable without a socket.
"""
from __future__ import annotations

import html
import http.server
import secrets
import socketserver
import threading
import urllib.parse
import webbrowser
from collections import Counter

from . import __version__, brand, interaction
from . import help as help_page
from .attribution import studies_with_edges
from .cytoscape import CytoscapeError, send
from .derive import ABSENCE_THRESHOLD, derive_interactions, genus_species, output_meta
from .export import to_graphml
from .growth import SPIKE_FACTOR
from .legend import legend_svg
from .mgrowthdb import MGrowthDBError, records_to_network
from .report import report_text
from .taxonomy import resolve_species, species_index

TITLE = brand.NAME
# species that derive a non-empty network, for the Example button (Karoline's proposal, #73). The first is
# taxon 411483, which mGrowthDB holds under both its names after the 2022 reclassification.
EXAMPLE = ("Faecalibacterium duncaniae", "Blautia hydrogenotrophica")
DEFAULTS = {"metric": "auc", "spike_factor": SPIKE_FACTOR, "absence_threshold": ABSENCE_THRESHOLD,
            "include_low_quality": False, "correction": "bh", "include_dropout": True,
            "include_non_batch": False, "studies": "", "only_entered": True,
            # None: the no-growth rule's own defaults, read when used (crossfeed.interaction.grew)
            "no_growth_alpha": None, "no_growth_factor": None}
PROVISIONAL = ("Each interaction compares a species' growth with and without its partner across replicates "
               "(mean log2 difference). An interaction is reported when |mean| is at least k standard "
               "deviations (the absence threshold, default 1: the mean plus or minus its standard deviation "
               "stays on one side of zero). Welch's t-test, corrected for multiple testing, is shown "
               "as supporting evidence and does not decide; with few replicates, more experiments may change "
               "any of these results (see docs/METHOD_NOTES.md).")
MISMATCH = ("Monoculture and co-culture growth were measured by different techniques in some of these "
            "studies, so neither the magnitude nor, near zero, the direction of those interactions is fully "
            "dependable.")
EMPTY_HELP = ("grownet derives interactions from pairwise (two-member) co-cultures and from drop-out "
              "designs (a community plus the same community without one member). Other larger communities "
              "yield nothing until a method suited to their design is chosen (see docs/METHOD_NOTES.md).")




def _page(body: str, token: str = "", refresh: str = "") -> str:
    """A page in the grownet style: a header with the mark, the name, the version, Legend and Help."""
    t = html.escape(token, quote=True)
    icon = urllib.parse.quote(brand.logo_svg(64))
    header = (f"<header><a class=\"brand\" href=\"/?token={t}\"><h1 class=\"brand\">{brand.logo_svg(28)}"
              f"{brand.WORDMARK}</h1></a>{HEADING}"
              f"<nav><a class=\"btn quiet\" href=\"/legend?token={t}\">Legend</a>"
              f"<a class=\"btn quiet\" href=\"/help?token={t}\">Help</a></nav></header>")
    # a running search reloads its page every second (#75): a meta refresh, so no JavaScript is needed
    reload = f"<meta http-equiv=\"refresh\" content=\"1; url={html.escape(refresh, quote=True)}\">" if refresh else ""
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>{TITLE}</title>"
            f"{reload}<link rel=\"icon\" href=\"data:image/svg+xml;utf8,{icon}\">"
            f"<style>{brand.CSS}</style></head><body><div class=\"app\">{header}<main>{body}</main></div>"
            "</body></html>\n")


def _esc(x) -> str:
    return html.escape(str(x), quote=True)


HEADING = f"<span class=\"version\">{html.escape(__version__)}</span>"


def _settings_block(settings: dict) -> str:
    """Every setting, collapsed behind one button. The plain page shows species and a submit button."""
    s = {**DEFAULTS, **settings}
    checked = " checked" if s["only_entered"] else ""
    low = " checked" if s["include_low_quality"] else ""
    dropout = " checked" if s["include_dropout"] else ""
    non_batch = " checked" if s["include_non_batch"] else ""
    corrections = "".join(f"<option value=\"{c}\"{' selected' if s['correction'] == c else ''}>{label}</option>"
                          for c, label in (("bh", "Benjamini-Hochberg"), ("by", "Benjamini-Yekutieli")))
    options = "".join(f"<option value=\"{m}\"{' selected' if s['metric'] == m else ''}>{m}</option>"
                      for m in ("auc", "max"))
    return f"""<details>
<summary>Advanced settings</summary>
<div class="row"><label>Growth measure
  <select name="metric">{options}</select></label>
  <span class="muted">the growth property compared: area under the curve (default) or maximal abundance</span></div>
<div class="row"><label><input type="checkbox" name="include_low_quality" value="1"{low}>
  Show low-quality edges</label>
  <span class="muted">pooled strains or an unclean drop-out; single-replicate edges are always shown,
  flagged</span></div>
<div class="row"><label><input type="checkbox" name="include_dropout" value="1"{dropout}>
  Include drop-out communities</label>
  <span class="muted">arcs from a community compared with the same community without one member; possibly
  indirect, so labeled as such</span></div>
<div class="row"><label><input type="checkbox" name="include_non_batch" value="1"{non_batch}>
  Include chemostat and serial dilution experiments</label>
  <span class="muted">excluded by default: a continuous-culture curve is not comparable with a batch
  one</span></div>
<div class="row"><label>Absence threshold k
  <input name="absence_threshold" type="text" size="6" value="{_esc(s['absence_threshold'])}"></label>
  <span class="muted">absent when |log2 mean| &lt; k &times; sd; 1 is mean &plusmn; sd, 0 marks none
  absent</span></div>
<div class="row"><label>Multiple testing correction
  <select name="correction">{corrections}</select></label>
  <span class="muted">Benjamini-Hochberg (default) or the more conservative Benjamini-Yekutieli</span></div>
<div class="row"><label>Spike limit
  <input name="spike_factor" type="text" size="6" value="{_esc(s['spike_factor'])}"></label>
  <span class="muted">leave out a curve with one or two points this many times above both neighbours;
  0 keeps all</span></div>
<div class="row"><label>No-growth alpha
  <input name="no_growth_alpha" type="text" size="6" value="{_esc(_no_growth(s, 'alpha'))}"></label>
  <span class="muted">a set has not grown when its rise from the first time point is not significant at
  this level (paired t-test); 0 switches the rule off</span></div>
<div class="row"><label>No-growth factor
  <input name="no_growth_factor" type="text" size="6" value="{_esc(_no_growth(s, 'factor'))}"></label>
  <span class="muted">a set that rose at least this many times (geometric mean over replicates) has
  grown whatever the test says; 0 leaves the test alone</span></div>
<div class="row"><label>Only these studies
  <input name="studies" type="text" size="40" value="{_esc(s['studies'])}"></label>
  <span class="muted">comma separated study ids; empty means every study holding the species</span></div>
<div class="row"><label><input type="checkbox" name="only_entered" value="1"{checked}>
  Only interactions between the species entered</label></div>
</details>"""


def render_form(token: str, entries: str = "", settings: dict | None = None, message: str = "",
                below: str = "", refresh: str = "") -> str:
    """The one page (#74): the species box, the settings, and under them whatever the search produced.

    `below` is the progress of a running search or its result, so the settings that produced a result stay
    on the page above it and can be changed and run again.
    """
    note = f"<p class=\"note\">{_esc(message)}</p>" if message else ""
    return _page(f"""{note}<form method="post" action="/run?token={_esc(token)}">
<label class="field" for="species">Species</label>
<textarea id="species" name="species" rows="5"
 placeholder="Faecalibacterium prausnitzii&#10;Blautia hydrogenotrophica">{_esc(entries)}</textarea>
<p class="hint">One per line. NCBI taxon ids work too. Interactions are derived from mGrowthDB growth data on
this machine; nothing is uploaded.</p>
<div class="bar"><button class="primary" type="submit">Find interactions</button>
<button type="submit" name="example" value="1">Example</button></div>
{_settings_block(settings or {})}
</form>{below}""", token, refresh)


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
                       refresh=f"/?token={token}&job={job['id']}")


def render_legend(token: str) -> str:
    """The legend inside the page frame, so every page carries the same header."""
    return _page(f"<div class=\"legend\">{legend_svg()}</div>"
                 f"<p class=\"bar\"><a class=\"btn\" href=\"/?token={_esc(token)}\">Back</a></p>", token)


def render_help(token: str) -> str:
    return _page(help_page.render_help(token, DEFAULTS, EXAMPLE)
                 + f"<p class=\"bar\"><a class=\"btn\" href=\"/?token={_esc(token)}\">Back</a></p>", token)


HEADER = ("<tr><th>source</th><th>affects</th><th>direction</th><th>log2 mean &plusmn; sd</th>"
          "<th>|mean| / sd</th><th>replicates with / without</th><th>adjusted p</th><th>condition</th>"
          "<th>remarks</th><th>study</th></tr>")


def _direction(e) -> str:
    """The effect, with obligate and abolished named, since they are the extremes of each direction."""
    if e.outcome == "obligate":
        return "facilitation (obligate)"
    if e.outcome == "abolished":
        return "inhibition (abolished)"
    return e.effect


def _number(x, fmt: str) -> str:
    return "" if x is None else format(x, fmt)


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
                    f"<td>{_number(e.effect_over_sd, '.2f')}</td>"
                    f"<td>{_esc(_number(e.n_with, 'd'))} / {_esc(_number(e.n_without, 'd'))}</td>"
                    f"<td>{_number(e.significance, '.3g')}</td><td>{_esc(e.condition)}</td>"
                    f"<td>{remarks}</td><td>{_esc(' '.join(e.study_ids))}</td></tr>")
    return "".join(rows)


def _hidden_note(hidden: dict) -> str:
    n = hidden.get("low_quality", 0)
    if not n:
        return ""
    return (f"<p class=\"muted\">Hidden by default: {n} low-quality edge(s). Tick them in Advanced settings "
            "to show them.</p>")


def _mean_sd(mean, sd) -> str:
    if mean is None:
        return ""
    return f"{mean:+.2f}" + ("" if sd is None else f" &plusmn; {sd:.2f}")


def _absent_section(net, absence: dict) -> str:
    """Edges below the absence threshold: kept and shown on request, apart from the interactions."""
    absent = [e for e in net.edges if e.status == "absent"]
    if not absent:
        return ""
    k = absence.get("k", ABSENCE_THRESHOLD)
    return (f"<details><summary>{len(absent)} edge(s) below the absence threshold (k = {k:g})</summary>"
            f"<p class=\"muted\">|log2 mean| &lt; {k:g} &times; sd: no interaction at this threshold. Kept in the "
            "downloads with status absent; the Cytoscape style hides them by default.</p>"
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
    """The three outputs Karoline asked for (#76): the network with a format menu, Cytoscape, the report."""
    t = _esc(token)
    download = (f"<form class=\"inline\" method=\"get\" action=\"/download\">"
                f"<input type=\"hidden\" name=\"token\" value=\"{t}\">"
                "<button class=\"primary\" type=\"submit\">Download network</button> "
                "<select name=\"format\" aria-label=\"Network format\">"
                "<option value=\"json\">JSON</option><option value=\"graphml\">GraphML</option></select></form>")
    cytoscape = (f"<form class=\"inline\" method=\"post\" action=\"/cytoscape?token={t}\">"
                 "<button type=\"submit\">Send to Cytoscape</button></form>")
    report = (f"<details class=\"report\"><summary class=\"btn\">Report</summary>"
              f"<pre>{_esc(report_text(result))}</pre>"
              f"<p><a class=\"btn\" href=\"/report.txt?token={t}\">Download the report (.txt)</a></p></details>")
    hint = ("<p class=\"hint\">Send to Cytoscape needs Cytoscape running on this machine; the network arrives in "
            "the legend's style. The report holds every setting and every reason a pair gave no edge.</p>")
    return (f"<div class=\"bar outputs\">{download if has_edges else ''}{cytoscape if has_edges else ''}"
            f"{report}</div>{hint if has_edges else ''}")


def _result_section(token: str, result: dict, message: str = "") -> str:
    resolved = "".join(
        f"<li>{_esc(entry)}: {_esc(', '.join(f'{name} ({tid})' for tid, name in sorted(matches.items())))}</li>"
        for entry, matches in result["resolved"])
    unresolved = ("<p>Not in mGrowthDB: " + _esc(", ".join(result["unresolved"])) + "</p>"
                  if result["unresolved"] else "")
    net = result["network"]
    mismatch = any("MISMATCH" in (e.method or "") for e in net.edges)
    hidden = _hidden_note(result.get("hidden", {}))
    shown = [e for e in net.edges if e.status != "absent"]
    note = f"<p class=\"note\">{_esc(message)}</p>" if message else ""
    outputs = _outputs(token, result, bool(net.edges))
    if shown:
        table = (f"<h2>{len(shown)} interaction(s)</h2>{outputs}"
                 f"<p class=\"note\">{PROVISIONAL}" + (f" {MISMATCH}" if mismatch else "") + "</p>"
                 f"{hidden}<div class=\"scroll\"><table>{HEADER}{_arc_rows(net, shown)}</table></div>")
    elif net.edges:
        table = (f"<h2>No interactions above the absence threshold</h2>{outputs}"
                 f"<p class=\"note\">{PROVISIONAL}</p>{hidden}")
    else:
        top = Counter(r.split(";")[0].strip() for _, r in result["skipped"]).most_common(1)
        why = f" Most common reason: {_esc(top[0][0])}." if top else ""
        table = ("<h2>No interactions</h2><p class=\"note\">Nothing was derived for these species."
                 f"{why} {EMPTY_HELP} <a href=\"/help?token={_esc(token)}#empty\">What to try</a>.</p>"
                 f"{hidden}{outputs}")
    studies = ", ".join(result["studies"]) or "none"
    skipped = ""
    if result["skipped"]:
        items = "".join(f"<li>{_esc(label)}: {_esc(reason)}</li>" for label, reason in result["skipped"][:50])
        skipped = (f"<details><summary>{len(result['skipped'])} pair(s) the data did not support</summary>"
                   f"<ul>{items}</ul></details>")
    errors = "".join(f"<p class=\"note\">{_esc(e)}</p>" for e in result["errors"])
    return (f"<section class=\"result\" id=\"result\">{note}<h2>Species</h2><ul>{resolved}</ul>{unresolved}"
            f"<p class=\"muted\">Studies searched: {_esc(studies)}</p>{errors}{table}"
            f"{_absent_section(net, result.get('absence', {}))}{_sources(net)}{skipped}</section>")


def render_result(token: str, result: dict, message: str = "") -> str:
    """The page with the result under the settings that produced it (#74)."""
    return render_form(token, "\n".join(result.get("entries", [])), result.get("settings"),
                       below=_result_section(token, result, message))


def _no_growth(s: dict, which: str) -> float:
    """A no-growth setting as the form shows it: the value chosen, or the rule's default."""
    value = s.get(f"no_growth_{which}")
    return value if value is not None else getattr(interaction, f"NO_GROWTH_{which.upper()}")


def parse_settings(form: dict) -> dict:
    """Settings from the posted form, falling back to the defaults for anything missing or unreadable."""
    settings = dict(DEFAULTS)
    metric = form.get("metric", [""])[0]
    if metric in ("auc", "max"):
        settings["metric"] = metric
    try:
        settings["spike_factor"] = abs(float(form.get("spike_factor", [""])[0]))
    except ValueError:
        pass
    settings["include_low_quality"] = bool(form.get("include_low_quality"))
    settings["include_dropout"] = bool(form.get("include_dropout"))
    settings["include_non_batch"] = bool(form.get("include_non_batch"))
    try:
        settings["absence_threshold"] = abs(float(form.get("absence_threshold", [""])[0]))
    except ValueError:
        pass
    for key in ("no_growth_alpha", "no_growth_factor"):
        try:
            settings[key] = abs(float(form.get(key, [""])[0]))
        except ValueError:
            pass
    correction = form.get("correction", [""])[0]
    if correction in ("bh", "by"):
        settings["correction"] = correction
    settings["studies"] = form.get("studies", [""])[0].strip()
    settings["only_entered"] = bool(form.get("only_entered"))
    return settings


def run_query(client, entries, settings: dict | None = None, index: dict | None = None, progress=None) -> dict:
    """Species names or taxon ids to an interaction network, through mGrowthDB and the existing derivation.

    Returns {"resolved", "unresolved", "taxon_ids", "studies", "network", "skipped", "errors"}. Failures
    that concern one study are collected in "errors" instead of raising, so a single bad study does not
    lose the rest. `progress(done, total, message)`, when given, is told where the search is: `total` is
    None until the studies are known (#75).
    """
    def say(done, total, message):
        if progress:
            progress(done, total, message)

    s = {**DEFAULTS, **(settings or {})}
    names = [line.strip() for line in entries if line and line.strip()]
    say(0, None, "Looking up the species in mGrowthDB")
    index = species_index(client) if index is None else index
    resolved = resolve_species(names, index)
    errors, skipped, records = [], [], []

    studies = [sid.strip() for sid in s["studies"].split(",") if sid.strip()]
    if resolved["taxon_ids"] and not studies:
        try:
            found = client.search(strain_ncbi_ids=",".join(str(t) for t in resolved["taxon_ids"]))
            studies = list(found.get("studies", []))
        except MGrowthDBError as e:
            errors.append(f"search failed: {e}")

    # A species name resolves to every strain of that species, and a strain keeps its taxon id across the
    # renamings mGrowthDB records (411483 is Faecalibacterium prausnitzii A2-165 in one study and
    # Faecalibacterium duncaniae A2-165 in others), so an edge is kept when either matches. Matching names
    # alone dropped every edge for a name the study does not use (#73).
    wanted = {genus_species(name) for _, matches in resolved["resolved"] for name in matches.values()}
    wanted_ids = {str(taxon) for taxon in resolved["taxon_ids"]}
    for i, study_id in enumerate(studies):
        say(i, len(studies), f"Reading {study_id} ({i + 1} of {len(studies)})")
        try:
            recs, skips = derive_interactions(client, study_id, metric=s["metric"],
                                              spike_factor=s["spike_factor"], dropout=s["include_dropout"],
                                              include_non_batch=s["include_non_batch"],
                                              no_growth_alpha=s["no_growth_alpha"],
                                              no_growth_factor=s["no_growth_factor"])
        except MGrowthDBError as e:
            errors.append(f"{study_id}: {e}")
            continue
        if s["only_entered"]:
            def entered(record, side):
                return (record.get(f"{side}_taxon_id") in wanted_ids
                        or record.get(f"{side}_species", record[side]) in wanted)

            recs = [r for r in recs if entered(r, "source") and entered(r, "target")]
        records += recs
        skipped += skips

    records, extra = output_meta(records, s["include_low_quality"], s["correction"], s["absence_threshold"],
                                 s["no_growth_alpha"], s["no_growth_factor"])
    # every setting the search ran with, so a downloaded network says how it was made (#78, #76)
    net = records_to_network(records, meta={
        "source_db": "mGrowthDB (live)", "species": names, "studies": studies, "settings": dict(s), **extra})
    say(len(studies), len(studies), "Preparing the result")
    return {"entries": names, "settings": dict(s), "resolved": resolved["resolved"],
            "unresolved": resolved["unresolved"], "taxon_ids": resolved["taxon_ids"], "studies": studies,
            "network": net,
            "skipped": skipped, "errors": errors, "hidden": extra["hidden"], "absence": extra["absence"]}


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

    def _send(self, body: str, content_type: str = "text/html; charset=utf-8", filename: str = ""):
        data = body.encode("utf-8")
        self.send_response(200)
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
        given = query.get("token", [""])[0]
        if secrets.compare_digest(given, self.token):
            return True
        self.send_error(403, "missing or wrong token; open the URL grownet printed")
        return False

    def _job_page(self, job_id: str) -> str:
        job = self.state.setdefault("jobs", {}).get(job_id)
        if job is None:
            return render_form(self.token, message="That search is no longer here; run it again.")
        if job["status"] == "running":
            return render_progress(self.token, job)
        if job["status"] == "failed":
            return render_form(self.token, "\n".join(job["entries"]), job["settings"], job["error"])
        self.state["result"] = job["result"]
        return render_result(self.token, job["result"])

    def _download(self, fmt: str):
        result = self.state.get("result")
        if not result:
            self._send(render_form(self.token, message="Nothing to download yet."))
        elif fmt == "graphml":
            self._send(to_graphml(result["network"]), "application/xml", f"{TITLE}_network.graphml")
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
        elif parsed.path == "/help":
            self._send(render_help(self.token))
        elif parsed.path == "/legend":
            self._send(render_legend(self.token))
        elif parsed.path == "/download":
            self._download(query.get("format", ["json"])[0])
        elif parsed.path in ("/download.json", "/download.graphml"):
            self._download(parsed.path.rsplit(".", 1)[1])
        elif parsed.path == "/report.txt":
            result = self.state.get("result")
            if not result:
                self._send(render_form(self.token, message="No report yet: run a search first."))
            else:
                self._send(report_text(result), "text/plain; charset=utf-8", f"{TITLE}_report.txt")
        else:
            self.send_error(404, "no such page")

    def _to_cytoscape(self) -> str:
        """Send the network already computed, without deriving it again (#25)."""
        result = self.state.get("result")
        if not result:
            return render_form(self.token, message="Nothing to send yet.")
        try:
            sent = send(result["network"], name=TITLE)
        except CytoscapeError as e:
            return render_result(self.token, result, message=str(e))
        return render_result(self.token, result,
                             message=f"Sent to Cytoscape: network {sent['suid']}, styled.")

    def _start(self, entries: list, settings: dict) -> dict:
        """Run a search in a thread, so the page can show its progress while it runs (#75)."""
        job = {"id": secrets.token_hex(4), "status": "running", "done": 0, "total": None,
               "message": "Starting", "entries": [e.strip() for e in entries if e.strip()],
               "settings": settings, "result": None, "error": ""}

        def progress(done, total, message):
            job.update(done=done, total=total, message=message)

        def work():
            try:
                client = self.client_factory()
                if self.state.get("index") is None:
                    # the species list of all of mGrowthDB: slow to build, so built once per session
                    progress(0, None, "Reading the species list of mGrowthDB (the first search only)")
                    self.state["index"] = species_index(client)
                job["result"] = run_query(client, entries, settings, self.state["index"], progress=progress)
                job["status"] = "done"
            except MGrowthDBError as e:
                job.update(status="failed", error=f"mGrowthDB is not reachable: {e}")
            except Exception as e:             # a bug must reach the page, not only a dead thread
                job.update(status="failed", error=f"The search failed: {type(e).__name__}: {e}")

        self.state.setdefault("jobs", {})[job["id"]] = job
        job["thread"] = threading.Thread(target=work, daemon=True)
        job["thread"].start()
        return job

    def do_POST(self):            # noqa: N802 - the name http.server requires
        parsed = urllib.parse.urlparse(self.path)
        if not self._authorized(urllib.parse.parse_qs(parsed.query)):
            return
        if parsed.path == "/cytoscape":
            self._send(self._to_cytoscape())
            return
        length = int(self.headers.get("Content-Length") or 0)
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
        entries = form.get("species", [""])[0].splitlines()
        settings = parse_settings(form)
        if form.get("example"):
            self._send(render_form(self.token, "\n".join(EXAMPLE), settings))
            return
        if not [e for e in entries if e.strip()]:
            self._send(render_form(self.token, settings=settings, message="Type at least one species."))
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
        raise SystemExit(f"crossfeed gui: cannot use port {port} ({e.strerror}). Pick another with --port, "
                         "or leave it out to use a free one.") from None
    with server as httpd:
        url = f"http://127.0.0.1:{httpd.server_address[1]}/?token={handler.token}"
        print(f"{TITLE} is at {url}\nPress Ctrl+C to stop.")
        if open_browser:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
