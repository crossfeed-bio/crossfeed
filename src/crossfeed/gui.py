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

from .derive import DEADBAND, derive_interactions, genus_species
from .export import to_graphml
from .mgrowthdb import MGrowthDBError, records_to_network
from .taxonomy import resolve_species, species_index

TITLE = "crossfeed"
DEFAULTS = {"metric": "growthRate", "deadband": DEADBAND, "studies": "", "only_entered": True}
EMPTY_HELP = ("The provisional baseline handles pairwise (two-member) co-cultures only, so studies built "
              "on larger or deletion consortia yield nothing until a method suited to their design is "
              "chosen (see docs/METHOD_NOTES.md).")

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
    options = "".join(f"<option value=\"{m}\"{' selected' if s['metric'] == m else ''}>{m}</option>"
                      for m in ("growthRate", "auc"))
    return f"""<details>
<summary>Advanced settings</summary>
<div class="row"><label>Growth measure
  <select name="metric">{options}</select></label>
  <span class="muted">what a strain's growth is read from (default growthRate)</span></div>
<div class="row"><label>Neutral range
  <input name="deadband" type="text" size="6" value="{_esc(s['deadband'])}"></label>
  <span class="muted">a log2 change smaller than this counts as neutral</span></div>
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


def _arc_rows(net) -> str:
    rows = []
    for e in net.edges:
        strength = "" if e.strength is None else f"{e.strength:+.2f}"
        rows.append(f"<tr><td>{_esc(net.nodes[e.source].name or e.source)}</td>"
                    f"<td>{_esc(net.nodes[e.target].name or e.target)}</td>"
                    f"<td>{_esc(e.effect)}</td><td>{_esc(strength)}</td>"
                    # evidence arrives with #17; until then the column stays empty
                    f"<td>{_esc(getattr(e, 'evidence', None) or '')}</td>"
                    f"<td>{_esc(' '.join(e.study_ids))}</td></tr>")
    return "".join(rows)


def render_result(token: str, result: dict) -> str:
    resolved = "".join(
        f"<li>{_esc(entry)}: {_esc(', '.join(f'{name} ({tid})' for tid, name in sorted(matches.items())))}</li>"
        for entry, matches in result["resolved"])
    unresolved = ("<p>Not in mGrowthDB: " + _esc(", ".join(result["unresolved"])) + "</p>"
                  if result["unresolved"] else "")
    net = result["network"]
    if net.edges:
        table = (f"<h2>{len(net.edges)} interaction(s)</h2>"
                 "<table><tr><th>source</th><th>affects</th><th>effect</th><th>log2 strength</th>"
                 f"<th>evidence</th><th>study</th></tr>{_arc_rows(net)}</table>"
                 f"<p><a href=\"/download.json?token={_esc(token)}\">Download JSON</a> &middot; "
                 f"<a href=\"/download.graphml?token={_esc(token)}\">Download GraphML</a></p>")
    else:
        top = Counter(r.split(";")[0].strip() for _, r in result["skipped"]).most_common(1)
        why = f" Most common reason: {_esc(top[0][0])}." if top else ""
        table = ("<h2>No interactions</h2><p class=\"note\">Nothing was derived for these species."
                 f"{why} {EMPTY_HELP}</p>")
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
{errors}{table}{skipped}
<p><a href="/?token={_esc(token)}">New search</a></p>""")


def parse_settings(form: dict) -> dict:
    """Settings from the posted form, falling back to the defaults for anything missing or unreadable."""
    settings = dict(DEFAULTS)
    metric = form.get("metric", [""])[0]
    if metric in ("growthRate", "auc"):
        settings["metric"] = metric
    try:
        settings["deadband"] = abs(float(form.get("deadband", [""])[0]))
    except ValueError:
        pass
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
            recs, skips = derive_interactions(client, study_id, metric=s["metric"], deadband=s["deadband"])
        except MGrowthDBError as e:
            errors.append(f"{study_id}: {e}")
            continue
        if s["only_entered"]:
            recs = [r for r in recs if r["source"] in wanted and r["target"] in wanted]
        records += recs
        skipped += skips

    net = records_to_network(records, meta={"source_db": "mGrowthDB (live)", "species": names,
                                            "studies": studies})
    return {"resolved": resolved["resolved"], "unresolved": resolved["unresolved"],
            "taxon_ids": resolved["taxon_ids"], "studies": studies, "network": net,
            "skipped": skipped, "errors": errors}


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
