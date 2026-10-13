"""The All network, derived once a day and published from this repository (#96).

Karoline (2026-09-28): "For the All network, could we build it, save it in grownet's github, serve from
there if less than a day old", and "let's serve the All network from the grownet repository". A copy of
grownet cannot write to GitHub (it would need a credential anyone could take), and the repository holds
no data from mGrowthDB (AGENTS.md). So a scheduled workflow (.github/workflows/all-network.yml) derives
All with the default settings and replaces one file on a fixed release, outside git history; the page's
All button and `grownet derive --all` read that file when it is less than `MAX_AGE` (36 hours) old and
the settings are the defaults, and otherwise derive live, as before. Nothing is ever uploaded by a user's
copy.

The file holds the whole result of the search, not only the network, so the page shows it as a live
result: the arcs, the arcs the absence threshold left out, the studies, the pairs the data did not
support, the growth rates and any steady-state check, and the report. `FIELDS` is that list and the
module's claim is only as true as it; three of them were missing until 2026-10-11 (#228).
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import urllib.request

from .model import SCHEMA, InteractionNetwork

FORMAT = "grownet.all_result/v1"
RELEASE_TAG = "all-network"
# The file a copy of grownet fetches is named by the format id it reads, so a format move never strands
# an installed copy (Karoline, 2026-10-12, on #289: "Publish both"). Copies before /v4 fetch the bare
# `all_result.json`, which the workflow keeps writing for them as /v3 (`packaging/publish_all.py`).
FILE = f"all_result.{SCHEMA.rsplit('/', 1)[-1]}.json"
URL = f"https://github.com/crossfeed-bio/crossfeed/releases/download/{RELEASE_TAG}/{FILE}"
# 36 hours, not one day (Karoline, 2026-10-12, on #196: "Extend to 36 hours"). The workflow runs once a
# day and GitHub starts scheduled runs late by a varying amount: the gap between two published artifacts
# reached 27h20m (first hand run to first scheduled one), and 7 of 12 consecutive scheduled runs ended more
# than 24 hours after the one before (measured 2026-10-12; 6 of 12 by start time), so with a one-day
# window the file went stale most nights before its replacement landed, and every copy of grownet derived
# All live from mGrowthDB at once, which is the load the workflow exists to prevent. The format id and the
# derivation check are what keep a reader from a WRONG artifact; the age only bounds how old the data is,
# and mGrowthDB uploads are rare. Recorded in METHOD_NOTES item 30, which said one day before.
MAX_AGE = datetime.timedelta(hours=36)
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
    payload = {"format": FORMAT, "network": result["network"].to_dict(),
               "absent": absent.to_dict() if absent is not None else None,
               **{k: result.get(k) for k in FIELDS}}
    payload["identity"] = _identity(payload)
    return payload


def _identity(payload: dict) -> dict:
    """Something a reader can quote when asked which version of the daily artifact they used.

    The workflow replaces one file on a fixed release with `--clobber`, outside git history, so the file
    a reader downloaded is gone the next day and `derived_at` was its only identifier: a re-derive gives
    a different network from a database that has moved on, and the question "which version did you use"
    had no answer (#218 item 3).

    `content_sha256` is over the payload WITHOUT this block, so it is reproducible by a reader: dump the
    file, drop `identity`, canonicalize, hash. The run and the commit come from the environment GitHub
    Actions already provides, so the workflow needs no change, and a local run carries neither rather
    than inventing them.
    """
    body = json.dumps({k: v for k, v in payload.items() if k != "identity"},
                      sort_keys=True, separators=(",", ":"))
    return {"content_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "run": os.environ.get("GITHUB_RUN_ID", ""),
            "commit": os.environ.get("GITHUB_SHA", ""),
            "hashed": "the payload with the identity block removed, JSON with sorted keys and no spaces"}


def from_payload(payload: dict) -> dict:
    """The search result a published file holds, with the date it was derived."""
    result = {k: payload.get(k) for k in FIELDS}
    result["skipped"] = [tuple(x) for x in payload.get("skipped") or []]
    result["resolved"] = [tuple(x) for x in payload.get("resolved") or []]
    result["network"] = InteractionNetwork.from_dict(payload["network"])
    absent = payload.get("absent")
    result["absent"] = InteractionNetwork.from_dict(absent) if absent else None
    result["identity"] = payload.get("identity") or {}
    result["published"] = result["network"].meta.get("derived_at", "")
    return result


def usable(settings: dict, defaults: dict) -> bool:
    """Whether a search can use the published network: All with every setting at its default, since that is
    the one the workflow derives."""
    return all(settings.get(k) == v for k, v in defaults.items())


def fresh(payload: dict, now: datetime.datetime | None = None, settings: dict | None = None) -> bool:
    """Whether a published file is this format, this schema, younger than `MAX_AGE`, and derived the way the
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
    return why_not_fresh(payload, now, settings) is None


def why_not_fresh(payload: dict, now: datetime.datetime | None = None, settings: dict | None = None) -> str | None:
    """Why a published file is not served, in a sentence for the page, or None when it is (#157).

    `fresh` said only True or False, and every failure looked the same to a reader: the All button derived
    live, and nothing said whether the file was old, from another version, or derived another way.
    """
    got = payload.get("format")
    if got != FORMAT:
        return f"it is in the format {got!r}, and this version of grownet reads {FORMAT!r}"
    schema = payload.get("network", {}).get("schema")
    if schema != SCHEMA:
        return f"its network is {schema!r}, and this version of grownet writes {SCHEMA!r}"
    if settings is not None:
        made_by = (payload.get("network", {}).get("meta", {}).get("settings") or {}).get("derivation")
        if made_by is not None and made_by != settings.get("derivation"):
            return (f"it was derived by the {made_by} derivation, and these settings ask for the "
                    f"{settings.get('derivation')} one")
    try:
        derived = datetime.datetime.fromisoformat(payload["network"]["meta"]["derived_at"])
    except (KeyError, TypeError, ValueError):
        return "it carries no time it was derived at"
    if derived.tzinfo is None:
        return "the time it was derived at has no offset"
    now = now or datetime.datetime.now(datetime.timezone.utc)
    age = now - derived
    if age < datetime.timedelta(0):
        return f"it says it was derived at {derived.isoformat()}, which is in the future"
    if age >= MAX_AGE:
        return (f"it is {age.total_seconds() / 3600:.0f} hours old, and it is served while less than "
                f"{MAX_AGE.total_seconds() / 3600:.0f} hours old")
    return None


def fetch(settings: dict | None = None, why: list | None = None) -> dict | None:
    """The published All result, or None when there is none, it is `MAX_AGE` old or more, it was derived
    by another derivation than `settings` asks for, or GitHub cannot be reached: the caller then derives
    live."""
    return fetch_from(urllib.request.urlopen, settings=settings, why=why)


def fetch_from(opener, now: datetime.datetime | None = None, settings: dict | None = None,
               why: list | None = None) -> dict | None:
    """`fetch` with the opener and the clock given, for tests.

    `why`, when given, receives the reason a None was returned. The broad `except` below is right for a
    fallback, and its cost was that a defect in `from_payload` or `fresh` looked exactly like a stale file,
    with nothing to tell them apart (Craig's agent, on #143; #157). A file that was fetched and could not
    be read now says so, and names the exception.
    """
    why = [] if why is None else why
    # every failure to read the published network is a reason to derive live, which is what the caller
    # does with None. `from_payload` is inside the guard because that is where an unreadable document
    # raises: a field a reader does not know used to come out of `Edge(**e)` as a TypeError, which is
    # neither OSError nor ValueError, so it left the All button by exception (Craig's agent, on #121).
    # #155 item 14 found the same thing on this branch, which did not yet carry #143's fix, so the two
    # lines fixed it independently; this is #143's wording, which is the one with the attribution.
    try:
        with opener(URL, timeout=TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as e:     # noqa: BLE001 - no artifact to read means derive live
        why.append(f"it could not be fetched from GitHub ({type(e).__name__}: {e})")
        return None
    try:
        reason = why_not_fresh(payload, now, settings)
        if reason:
            why.append(reason)
            return None
        return from_payload(payload)
    except Exception as e:     # noqa: BLE001 - any unreadable artifact means derive live
        why.append(f"it was fetched and could not be read ({type(e).__name__}: {e}). That is a defect in "
                   "this version of grownet rather than in the file's age, worth reporting")
        return None
