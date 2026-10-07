"""The All network, derived once a day and published from this repository (#96).

Karoline (2026-09-28): "For the All network, could we build it, save it in grownet's github, serve from
there if less than a day old", and "let's serve the All network from the grownet repository". A copy of
grownet cannot write to GitHub (it would need a credential anyone could take), and the repository holds
no data from mGrowthDB (AGENTS.md). So a scheduled workflow (.github/workflows/all-network.yml) derives
All with the default settings and replaces one file on a fixed release, outside git history; the page's
All button and `grownet derive --all` read that file when it is less than a day old and the settings are
the defaults, and otherwise derive live, as before. Nothing is ever uploaded by a user's copy.

The file holds the whole result of the search, not only the network, so the page shows it as a live
result: the arcs, the studies, the pairs the data did not support, and the report.
"""
from __future__ import annotations

import datetime
import json
import urllib.request

from .model import SCHEMA, InteractionNetwork

FORMAT = "grownet.all_result/v1"
RELEASE_TAG = "all-network"
FILE = "all_result.json"
URL = f"https://github.com/crossfeed-bio/crossfeed/releases/download/{RELEASE_TAG}/{FILE}"
MAX_AGE = datetime.timedelta(days=1)
TIMEOUT = 15
# the parts of a search result the file carries, besides the network
FIELDS = ("entries", "settings", "resolved", "reasons", "suggestions", "excluded", "all", "genera",
          "partners_only", "unresolved", "taxon_ids", "studies", "skipped", "errors", "hidden", "absence")


def to_payload(result: dict) -> dict:
    """A search result of All as one JSON document."""
    return {"format": FORMAT, "network": result["network"].to_dict(),
            **{k: result.get(k) for k in FIELDS}}


def from_payload(payload: dict) -> dict:
    """The search result a published file holds, with the date it was derived."""
    result = {k: payload.get(k) for k in FIELDS}
    result["skipped"] = [tuple(x) for x in payload.get("skipped") or []]
    result["resolved"] = [tuple(x) for x in payload.get("resolved") or []]
    result["network"] = InteractionNetwork.from_dict(payload["network"])
    result["published"] = result["network"].meta.get("derived_at", "")
    return result


def usable(settings: dict, defaults: dict) -> bool:
    """Whether a search can use the published network: All with every setting at its default, since that is
    the one the workflow derives."""
    return all(settings.get(k) == v for k, v in defaults.items())


def fresh(payload: dict, now: datetime.datetime | None = None) -> bool:
    """Whether a published file is this format, this schema, and less than a day old."""
    if payload.get("format") != FORMAT or payload.get("network", {}).get("schema") != SCHEMA:
        return False
    try:
        derived = datetime.datetime.fromisoformat(payload["network"]["meta"]["derived_at"])
    except (KeyError, TypeError, ValueError):
        return False
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return derived.tzinfo is not None and datetime.timedelta(0) <= now - derived < MAX_AGE


def fetch() -> dict | None:
    """Today's published All result, or None when there is none, it is a day old or more, or GitHub cannot
    be reached: the caller then derives live."""
    return fetch_from(urllib.request.urlopen)


def fetch_from(opener, now: datetime.datetime | None = None) -> dict | None:
    """`fetch` with the opener and the clock given, for tests."""
    # every failure to read the published network is a reason to derive live, which is what the caller
    # does with None. `from_payload` is inside the guard because that is where an unreadable document
    # raises: a field a reader does not know used to come out of `Edge(**e)` as a TypeError, which is
    # neither OSError nor ValueError, so it left the All button by exception (Craig's agent, on #121).
    try:
        with opener(URL, timeout=TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return from_payload(payload) if fresh(payload, now) else None
    except Exception:          # noqa: BLE001 - any unreadable artifact means derive live
        return None
