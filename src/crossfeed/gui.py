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
import urllib.parse
import webbrowser
from collections import Counter

from .attribution import studies_with_edges
from .derive import ABSENCE_THRESHOLD, derive_interactions, genus_species, output_meta
from .export import to_graphml
from .growth import SPIKE_FACTOR
from .mgrowthdb import MGrowthDBError, records_to_network
from .taxonomy import resolve_species, species_index

TITLE = "crossfeed"
DEFAULTS = {"metric": "auc", "spike_factor": SPIKE_FACTOR, "absence_threshold": ABSENCE_THRESHOLD,
            "include_low_quality": False, "correction": "bh", "include_dropout": True, "studies": "",
            "only_entered": True}
PROVISIONAL = ("Each interaction compares a species' growth with and without its partner across replicates "
               "(mean log2 difference). An interaction is reported when |mean| is at least k standard "
               "deviations (the absence threshold, default 1: the mean plus or minus its standard deviation "
               "stays on one side of zero). Welch's t-test, corrected for multiple testing, is shown "
               "as supporting evidence and does not decide; with few replicates, more experiments may change "
               "any of these results (see docs/METHOD_NOTES.md).")
MISMATCH = ("Monoculture and co-culture growth were measured by different techniques in some of these "
            "studies, so neither the magnitude nor, near zero, the direction of those interactions is fully "
            "dependable.")
EMPTY_HELP = ("crossfeed derives interactions from pairwise (two-member) co-cultures and from drop-out "
              "designs (a community plus the same community without one member). Other larger communities "
              "yield nothing until a method suited to their design is chosen (see docs/METHOD_NOTES.md).")

CSS = """
body { font: 16px/1.5 system-ui, sans-serif; margin: 0 auto; max-width: 52rem; padding: 2rem 1rem; }
h1 { font-size: 1.4rem; } h2 { font-size: 1.1rem; margin-top: 2rem; }
textarea, input, select { font: inherit; } textarea { width: 100%; }
button { font: inherit; padding: 0.4rem 1.2rem; margin-top: 0.8rem; }
table { border-collapse: collapse; width: 100%; margin-top: 0.5rem; }
th, td { border-bottom: 1px solid #ddd; padding: 0.3rem 0.5rem; text-align: left; vertical-align: top; }
details { margin-top: 1rem; } summary { cursor: pointer; }
.row { margin: 0.4rem 0; } .muted { color: #555; font-size: 0.9rem; }
.note { background: #f4f4f4; padding: 0.8rem 1rem; border-radius: 4px; }
.sources { font-size: 0.9rem; } .sources li { margin-bottom: 0.3rem; }
"""


def _page(body: str) -> str:
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>{TITLE}</title>"
            f"<style>{CSS}</style></head><body>{body}</body></html>\n")


def _esc(x) -> str:
    return html.escape(str(x), quote=True)


def _settings_block(settings: dict) -> str:
    """Every setting, collapsed behind one button. The plain page shows species and a submit button."""
    s = {**DEFAULTS, **settings}
    checked = " checked" if s["only_entered"] else ""
    low = " checked" if s["include_low_quality"] else ""
    dropout = " checked" if s["include_dropout"] else ""
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
<div class="row"><label>Only these studies
  <input name="studies" type="text" size="40" value="{_esc(s['studies'])}"></label>
  <span class="muted">comma separated study ids; empty means every study holding the species</span></div>
<div class="row"><label><input type="checkbox" name="only_entered" value="1"{checked}>
  Only interactions between the species entered</label></div>
</details>"""


def render_form(token: str, entries: str = "", settings: dict | None = None, message: str = "") -> str:
    note = f"<p class=\"note\">{_esc(message)}</p>" if message else ""
    return _page(f"""<h1>crossfeed</h1>
<p>Type species names, one per line. NCBI taxon ids work too.</p>{note}
<form method="post" action="/run?token={_esc(token)}">
<textarea name="species" rows="6" placeholder="Faecalibacterium prausnitzii&#10;Blautia hydrogenotrophica"
>{_esc(entries)}</textarea>
{_settings_block(settings or {})}
<button type="submit">Find interactions</button>
</form>
<p class="muted">Interactions are derived from mGrowthDB growth data on this machine. Nothing is uploaded.</p>""")


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
        remarks = "; ".join([*(["drop-out community, possibly indirect"] if e.evidence == "dropout" else []),
                             *(f"low quality: {q.replace('_', ' ')}" for q in e.quality),
                             *(f"caution: {c.replace('_', ' ')}" for c in e.cautions), *e.notes])
        rows.append(f"<tr><td>{_esc(net.nodes[e.source].name or e.source)}</td>"
                    f"<td>{_esc(net.nodes[e.target].name or e.target)}</td>"
                    f"<td>{_esc(_direction(e))}</td><td>{_mean_sd(e.strength, e.sd)}</td>"
                    f"<td>{_number(e.effect_over_sd, '.2f')}</td>"
                    f"<td>{_esc(_number(e.n_with, 'd'))} / {_esc(_number(e.n_without, 'd'))}</td>"
                    f"<td>{_number(e.significance, '.3g')}</td><td>{_esc(e.condition)}</td>"
                    f"<td>{_esc(remarks)}</td><td>{_esc(' '.join(e.study_ids))}</td></tr>")
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
            f"<table>{HEADER}{_arc_rows(net, absent)}</table></details>")


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


def render_result(token: str, result: dict) -> str:
    resolved = "".join(
        f"<li>{_esc(entry)}: {_esc(', '.join(f'{name} ({tid})' for tid, name in sorted(matches.items())))}</li>"
        for entry, matches in result["resolved"])
    unresolved = ("<p>Not in mGrowthDB: " + _esc(", ".join(result["unresolved"])) + "</p>"
                  if result["unresolved"] else "")
    net = result["network"]
    mismatch = any("MISMATCH" in (e.method or "") for e in net.edges)
    hidden = _hidden_note(result.get("hidden", {}))
    shown = [e for e in net.edges if e.status != "absent"]
    downloads = (f"<p><a href=\"/download.json?token={_esc(token)}\">Download JSON</a> &middot; "
                 f"<a href=\"/download.graphml?token={_esc(token)}\">Download GraphML</a></p>")
    if shown:
        table = (f"<h2>{len(shown)} interaction(s)</h2>"
                 f"<p class=\"note\">{PROVISIONAL}" + (f" {MISMATCH}" if mismatch else "") + "</p>"
                 f"{hidden}<table>{HEADER}{_arc_rows(net, shown)}</table>{downloads}")
    elif net.edges:
        table = ("<h2>No interactions above the absence threshold</h2>"
                 f"<p class=\"note\">{PROVISIONAL}</p>{hidden}{downloads}")
    else:
        top = Counter(r.split(";")[0].strip() for _, r in result["skipped"]).most_common(1)
        why = f" Most common reason: {_esc(top[0][0])}." if top else ""
        table = ("<h2>No interactions</h2><p class=\"note\">Nothing was derived for these species."
                 f"{why} {EMPTY_HELP}</p>{hidden}")
    studies = ", ".join(result["studies"]) or "none"
    skipped = ""
    if result["skipped"]:
        items = "".join(f"<li>{_esc(label)}: {_esc(reason)}</li>" for label, reason in result["skipped"][:50])
        skipped = (f"<details><summary>{len(result['skipped'])} pair(s) the data did not support</summary>"
                   f"<ul>{items}</ul></details>")
    errors = "".join(f"<p class=\"note\">{_esc(e)}</p>" for e in result["errors"])
    return _page(f"""<h1>crossfeed</h1>
<h2>Species</h2><ul>{resolved}</ul>{unresolved}
<p class="muted">Studies searched: {_esc(studies)}</p>
{errors}{table}{_absent_section(net, result.get("absence", {}))}{_sources(net)}{skipped}
<p><a href="/?token={_esc(token)}">New search</a></p>""")


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
    try:
        settings["absence_threshold"] = abs(float(form.get("absence_threshold", [""])[0]))
    except ValueError:
        pass
    correction = form.get("correction", [""])[0]
    if correction in ("bh", "by"):
        settings["correction"] = correction
    settings["studies"] = form.get("studies", [""])[0].strip()
    settings["only_entered"] = bool(form.get("only_entered"))
    return settings


def run_query(client, entries, settings: dict | None = None, index: dict | None = None) -> dict:
    """Species names or taxon ids to an interaction network, through mGrowthDB and the existing derivation.

    Returns {"resolved", "unresolved", "taxon_ids", "studies", "network", "skipped", "errors"}. Failures
    that concern one study are collected in "errors" instead of raising, so a single bad study does not
    lose the rest.
    """
    s = {**DEFAULTS, **(settings or {})}
    names = [line.strip() for line in entries if line and line.strip()]
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

    wanted = {genus_species(name) for _, matches in resolved["resolved"] for name in matches.values()}
    for study_id in studies:
        try:
            recs, skips = derive_interactions(client, study_id, metric=s["metric"],
                                              spike_factor=s["spike_factor"], dropout=s["include_dropout"])
        except MGrowthDBError as e:
            errors.append(f"{study_id}: {e}")
            continue
        if s["only_entered"]:
            recs = [r for r in recs if r["source"] in wanted and r["target"] in wanted]
        records += recs
        skipped += skips

    records, extra = output_meta(records, s["include_low_quality"], s["correction"], s["absence_threshold"])
    net = records_to_network(records, meta={
        "source_db": "mGrowthDB (live)", "species": names, "studies": studies, **extra})
    return {"resolved": resolved["resolved"], "unresolved": resolved["unresolved"],
            "taxon_ids": resolved["taxon_ids"], "studies": studies, "network": net,
            "skipped": skipped, "errors": errors, "hidden": extra["hidden"], "absence": extra["absence"]}


class _Handler(http.server.BaseHTTPRequestHandler):
    """Routes: the form, a run, and the two downloads. Every request carries the session token."""

    token = ""
    client_factory = None
    state: dict = {}

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

    def _authorized(self, query: dict) -> bool:
        given = query.get("token", [""])[0]
        if secrets.compare_digest(given, self.token):
            return True
        self.send_error(403, "missing or wrong token; open the URL crossfeed printed")
        return False

    def do_GET(self):             # noqa: N802 - the name http.server requires
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if not self._authorized(query):
            return
        if parsed.path == "/":
            self._send(render_form(self.token))
        elif parsed.path in ("/download.json", "/download.graphml"):
            result = self.state.get("result")
            if not result:
                self._send(render_form(self.token, message="Nothing to download yet."))
                return
            if parsed.path.endswith(".json"):
                self._send(result["network"].to_json(), "application/json", "crossfeed_network.json")
            else:
                self._send(to_graphml(result["network"]), "application/xml", "crossfeed_network.graphml")
        else:
            self.send_error(404, "no such page")

    def do_POST(self):            # noqa: N802 - the name http.server requires
        parsed = urllib.parse.urlparse(self.path)
        if not self._authorized(urllib.parse.parse_qs(parsed.query)):
            return
        length = int(self.headers.get("Content-Length") or 0)
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))
        entries = form.get("species", [""])[0].splitlines()
        settings = parse_settings(form)
        if not [e for e in entries if e.strip()]:
            self._send(render_form(self.token, settings=settings, message="Type at least one species."))
            return
        try:
            result = run_query(self.client_factory(), entries, settings, self.state.get("index"))
        except MGrowthDBError as e:
            self._send(render_form(self.token, "\n".join(entries), settings, f"mGrowthDB is not reachable: {e}"))
            return
        self.state["result"] = result
        self._send(render_result(self.token, result))


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
    with _Server(("127.0.0.1", port), handler) as httpd:
        url = f"http://127.0.0.1:{httpd.server_address[1]}/?token={handler.token}"
        print(f"crossfeed is at {url}\nPress Ctrl+C to stop.")
        if open_browser:
            webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
