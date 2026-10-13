"""Derive the All network of mGrowthDB with the default settings, for the daily release asset (#96).

Run by .github/workflows/all-network.yml, which uploads the files it writes to the `all-network` release.
Usage: python packaging/publish_all.py OUT_DIR [NOTES_FILE]
Writes all_result.<format>.json (what the page and `grownet derive --all` read), all_result.json (the same as
the older format installed copies read), all_network.json and all_report.txt,
and, when given NOTES_FILE, the release description for this run, which the workflow sets on every run.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from grownet.gui import DEFAULTS, run_query
from grownet.mgrowthdb import MGrowthDBClient
from grownet.published import FILE, MAX_AGE, RELEASE_TAG, TIMEOUT, URL, _identity, to_payload
from grownet.report import report_text

ROOT = Path(__file__).resolve().parents[1]

# What installed 0.3.x and 0.4.x copies fetch and accept: `published.fresh` there requires the network's
# schema id to equal their own, /v3, so the /v4 artifact would send every one of them to derive All live
# from mGrowthDB until upgraded, which is the load the daily file exists to prevent (Craig's agent, on
# #289). /v4 only ADDED fields, so the same artifact with those fields removed IS a /v3 document, and it is
# written under the name those copies already fetch (Karoline, 2026-10-12: "Publish both").
LEGACY = {"file": "all_result.json", "schema": "grownet.interaction_network/v3"}
LEGACY_URL = f"https://github.com/crossfeed-bio/crossfeed/releases/download/{RELEASE_TAG}/{LEGACY['file']}"


def legacy_payload(payload: dict, legacy_schema: str = LEGACY["schema"]) -> dict:
    """`payload` as a `legacy_schema` document: every node, edge and study field that format does not
    declare is removed, read from `schema/format_fields.json`, and the identity is recomputed for it.

    Only a format that was ADDED to can be written down this way; a changed meaning cannot be removed by
    dropping a field, so the manifest's entry for the legacy id is the whole contract.
    """
    declared = json.loads((ROOT / "schema" / "format_fields.json").read_text(encoding="utf-8"))
    fields = declared["formats"][legacy_schema]
    out = json.loads(json.dumps(payload))

    def strip(network):
        if not isinstance(network, dict):
            return
        network["schema"] = legacy_schema
        for key, kind in (("nodes", "node"), ("edges", "edge"), ("studies", "study")):
            network[key] = [{k: v for k, v in item.items() if k in set(fields[kind])}
                            for item in network.get(key, [])]
    strip(out.get("network"))
    strip(out.get("absent"))
    out.pop("identity", None)
    out["identity"] = _identity(out)
    return out

NETWORK, REPORT = "all_network.json", "all_report.txt"

# A run that keeps less than this share of the previous artifact's arcs is refused unless the run says
# the drop is meant (#236). Half is far below anything a data update has done, and far above zero. A
# derivation can collapse to nothing (the three settings #220 lists do it, and a code or API change could
# do it at the defaults), and a collapsed one published, passed `fresh`, and was served to every reader
# at the defaults until the next run.
MIN_SHARE_OF_PREVIOUS = 0.5


def previous_arcs(opener=urllib.request.urlopen) -> int | str | None:
    """How many arcs the artifact being replaced carries; None when there is none (GitHub answers 404,
    which is the first run); or, as a string, why it could not be read.

    The floor fails CLOSED on the last (Craig's agent, on #275): a timeout, a 503 or a truncated body is
    not "no previous artifact" but "cannot tell whether this run collapsed", and it used to switch the
    half check off on exactly the night it might be needed.
    """
    # the first run under a new format id has no file of its own yet, so it compares with the legacy file
    for url in (URL, LEGACY_URL):
        try:
            with opener(url, timeout=TIMEOUT) as response:
                return len(json.loads(response.read().decode("utf-8"))["network"]["edges"])
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            return f"GitHub answered HTTP {e.code}"
        except Exception as e:     # noqa: BLE001 - every other failure is reported, and refuses below
            return f"{type(e).__name__}: {e}"
    return None


def floor(arcs: int, previous: int | None, allow_drop: bool = False) -> list:
    """Why this run must not be published, or [] when it may (#236).

    The workflow gated on `result["errors"]` alone, so a derivation that collapsed to zero arcs published
    successfully and its release text, "Every arc cites the studies it comes from", was vacuously true.
    """
    if arcs == 0:
        return ["the derivation produced no arcs at all, which no data update explains"]
    if isinstance(previous, str) and not allow_drop:
        return [f"the artifact this run would replace could not be read ({previous}), so a collapse cannot "
                "be ruled out. If GitHub was only unreachable, run the workflow again, or by hand with "
                "allow_drop set"]
    if isinstance(previous, int) and previous and arcs < MIN_SHARE_OF_PREVIOUS * previous and not allow_drop:
        return [f"the derivation produced {arcs} arcs where the artifact it would replace has {previous}, "
                f"less than {MIN_SHARE_OF_PREVIOUS:.0%} of them. If that is meant, run the workflow by hand "
                "with allow_drop set"]
    return []


def _age(max_age) -> str:
    hours = max_age.total_seconds() / 3600
    return "less than a day old" if hours == 24 else f"less than {hours:g} hours old"


def release_notes(result: dict) -> str:
    """The release description for this run.

    It used to be written once, by `gh release create`, on the first run (2026-09-29), so editing it in the
    workflow changed nothing, and it promised "the default settings" for two files nothing checks (#236).
    Now every run sets it, it says what this run produced, and which file the freshness rule governs.
    """
    net = result["network"]
    meta = net.meta
    derivation = (meta.get("settings") or {}).get("derivation", "unknown")
    return f"""The All network of mGrowthDB, derived with grownet's default settings by \
`.github/workflows/all-network.yml` and replaced by each run. Every run rewrites this description, so it \
describes the files below as they are now.

**This run:** {len(result['studies'])} studies, {len(net.nodes)} organisms, {len(net.edges)} arcs, derived \
at {meta.get('derived_at')} by grownet {meta.get('tool_version')}, derivation `{derivation}`.

- `{FILE}` is the file grownet reads. A copy of grownet uses it only when it is {_age(MAX_AGE)}, written \
in the format and schema that copy reads, and derived by the derivation the copy's settings ask for; \
otherwise that copy derives All live from mGrowthDB.
- `{LEGACY['file']}` is the same network for copies that read the older `{LEGACY['schema']}`: the fields \
added since are removed and nothing else differs, so an installed copy keeps reading the daily file until \
it is upgraded.
- `{NETWORK}` and `{REPORT}` are the same network and its report, for reading. **Nothing checks these two \
against the grownet you have**: a file downloaded by hand is whatever the last run produced, so read \
`meta.tool_version`, `meta.build` (the commit), `meta.derived_at` and `meta.settings.derivation` inside \
`{NETWORK}` before comparing it with your own derivation.

Every arc cites the studies it comes from, and the report lists them with their titles and DOIs.
"""


def main(out: str, notes: str | None = None, previous=previous_arcs) -> int:
    result = run_query(MGrowthDBClient(), [], dict(DEFAULTS), all_studies=True, published=False)
    if result["errors"]:
        print("not published, the derivation had errors:", *result["errors"], sep="\n  ", file=sys.stderr)
        return 1
    net = result["network"]
    refused = floor(len(net.edges), previous(), allow_drop=os.environ.get("ALLOW_DROP") == "true")
    if refused:
        print("not published:", *refused, sep="\n  ", file=sys.stderr)
        return 1
    # which code made this file, beside `tool_version`: the daily artifact is built from main's HEAD while
    # `__version__` stays at the last release, so two artifacts a week apart can carry one version and
    # different content, and only the commit says whether the tool or mGrowthDB changed (Craig's agent,
    # on #285). `all_result.json` had it in its `identity` block; `all_network.json`, the file a reader
    # downloads by hand, had nothing.
    if os.environ.get("GITHUB_SHA"):
        net.meta["build"] = {"commit": os.environ["GITHUB_SHA"], "run": os.environ.get("GITHUB_RUN_ID", "")}
    folder = Path(out)
    folder.mkdir(parents=True, exist_ok=True)
    payload = to_payload(result)
    (folder / FILE).write_text(json.dumps(payload) + "\n", encoding="utf-8")
    (folder / LEGACY["file"]).write_text(json.dumps(legacy_payload(payload)) + "\n", encoding="utf-8")
    (folder / NETWORK).write_text(net.to_json() + "\n", encoding="utf-8")
    (folder / REPORT).write_text(report_text(result), encoding="utf-8")
    if notes:
        Path(notes).write_text(release_notes(result), encoding="utf-8")
    print(f"All: {len(result['studies'])} studies, {len(net.nodes)} nodes, {len(net.edges)} arcs, "
          f"derived at {net.meta['derived_at']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
