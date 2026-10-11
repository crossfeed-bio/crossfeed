"""The All network, derived once a day and published from this repository (#96).

Karoline (2026-09-28): "For the All network, could we build it, save it in grownet's github, serve from
there if less than a day old", and "let's serve the All network from the grownet repository". A copy of
grownet cannot write to GitHub (it would need a credential anyone could take), and the repository holds
no data from mGrowthDB (AGENTS.md). So a scheduled workflow (.github/workflows/all-network.yml) derives
All with the default settings and replaces one file on a fixed release, outside git history; the page's
All button and `grownet derive --all` read that file when it is less than a day old and the settings are
the defaults, and otherwise derive live, as before. Nothing is ever uploaded by a user's copy.

The file holds the whole result of the search, not only the network, so the page shows it as a live
result: the arcs, the arcs the absence threshold left out, the studies, the pairs the data did not
support, the growth rates and any steady-state check, and the report. `FIELDS` is that list and the
module's claim is only as true as it; three of them were missing until 2026-10-11 (#228).
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
# The parts of a search result the file carries, besides the network. `absent` is handled separately
# because it is an InteractionNetwork rather than plain JSON, which is why it used to be dropped: the
# artifact's report stated "78 below the absence threshold" and its page section showed none of them,
# while the CLI's message for that condition says "The report lists them" (#228). `rates`, `steady` and
# `notes`, the advisory messages #242 split out of `errors`, went with it. A reader of the artifact now
# sees what a live run shows, and `tests/test_published.py` checks this list against what `run_query`
# returns rather than leaving it to be maintained by hand, which is how three went missing.
FIELDS = ("entries", "settings", "resolved", "reasons", "suggestions", "excluded", "all", "genera",
          "partners_only", "unresolved", "taxon_ids", "studies", "skipped", "errors", "hidden",
          "absence", "rates", "steady", "notes")


def to_payload(result: dict) -> dict:
    """A search result of All as one JSON document.

    `absent` is a network of its own, the arcs the absence threshold left out, so it is serialized the
    way `network` is rather than passed through as JSON.
    """
    absent = result.get("absent")
    return {"format": FORMAT, "network": result["network"].to_dict(),
            "absent": absent.to_dict() if absent is not None else None,
            **{k: result.get(k) for k in FIELDS}}


def from_payload(payload: dict) -> dict:
    """The search result a published file holds, with the date it was derived."""
    result = {k: payload.get(k) for k in FIELDS}
    result["skipped"] = [tuple(x) for x in payload.get("skipped") or []]
    result["resolved"] = [tuple(x) for x in payload.get("resolved") or []]
    result["network"] = InteractionNetwork.from_dict(payload["network"])
    absent = payload.get("absent")
    result["absent"] = InteractionNetwork.from_dict(absent) if absent else None
    result["published"] = result["network"].meta.get("derived_at", "")
    return result


def usable(settings: dict, defaults: dict) -> bool:
    """Whether a search can use the published network: All with every setting at its default, since that is
    the one the workflow derives."""
    return all(settings.get(k) == v for k, v in defaults.items())


def fresh(payload: dict, now: datetime.datetime | None = None, settings: dict | None = None) -> bool:
    """Whether a published file is this format, this schema, less than a day old, and derived the way the
    caller would derive it.

    **`settings` defaults to None, which skips the derivation check**, and that is stated here because the
    paragraph below makes that check the point of the function: measured on 2026-10-11, `fresh(p, now)`
    was True on the same artifact and at the same moment that `fresh(p, now, DEFAULTS)` was False, and
    `fetch()` with no argument returned the integrated artifact to a caller at the comparison (#235 item
    4). No shipped path does that, because `gui.run_query` passes the settings, and the default stays
    None so that a caller who genuinely has no settings (a reader inspecting an artifact) is not forced
    to invent some. A caller that will DERIVE from it passes them.

    **The derivation is checked because the schema id cannot see it.** The artifact and a live run can
    carry the same format, the same schema and entirely different networks: on 2026-10-10 the default
    went back to the comparison of replicate sets and the published artifact was still the integrated
    form's, 12 arcs against 145, with nothing between the reader and it. A format id moves when a FIELD
    changes meaning; which derivation filled the fields is not a field.
    """
    if payload.get("format") != FORMAT or payload.get("network", {}).get("schema") != SCHEMA:
        return False
    if settings is not None:
        made_by = (payload.get("network", {}).get("meta", {}).get("settings") or {}).get("derivation")
        if made_by is not None and made_by != settings.get("derivation"):
            return False
    try:
        derived = datetime.datetime.fromisoformat(payload["network"]["meta"]["derived_at"])
    except (KeyError, TypeError, ValueError):
        return False
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return derived.tzinfo is not None and datetime.timedelta(0) <= now - derived < MAX_AGE


def fetch(settings: dict | None = None) -> dict | None:
    """Today's published All result, or None when there is none, it is a day old or more, it was derived
    by another derivation than `settings` asks for, or GitHub cannot be reached: the caller then derives
    live."""
    return fetch_from(urllib.request.urlopen, settings=settings)


def fetch_from(opener, now: datetime.datetime | None = None, settings: dict | None = None) -> dict | None:
    """`fetch` with the opener and the clock given, for tests."""
    # every failure to read the published network is a reason to derive live, which is what the caller
    # does with None. `from_payload` is inside the guard because that is where an unreadable document
    # raises: a field a reader does not know used to come out of `Edge(**e)` as a TypeError, which is
    # neither OSError nor ValueError, so it left the All button by exception (Craig's agent, on #121).
    # #155 item 14 found the same thing on this branch, which did not yet carry #143's fix, so the two
    # lines fixed it independently; this is #143's wording, which is the one with the attribution.
    try:
        with opener(URL, timeout=TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return from_payload(payload) if fresh(payload, now, settings) else None
    except Exception:          # noqa: BLE001 - any unreadable artifact means derive live
        return None
