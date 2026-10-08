"""Send gLV parameters into a running R session (#110).

Karoline, 2026-10-03: "I'd like a companion plugin for R that would allow sending gLV parameters directly
to R via REST. The target simulator I have in mind is miaSim ... but it could also be another one or user
code (the plugin should not assume the presence of any particular simulator)."

The same shape as Send to Cytoscape, for the same reason: the R session opens a small port on this
machine, grownet POSTs the gLV payload (`grownet.matrix.glv_payload`) to it, and nothing is hosted and
nothing leaves the machine. The companion package is in `r/` of this repository; in R,
`grownet::grownet_listen()` is what answers here.

When nothing answers, the error says the other way round: the R package can fetch the same payload from
the page's own URL (`grownet::grownet_glv(url)`), so a user who cannot open a port is not stuck.
"""
from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.request

# The port the R package listens on by default. Not 1234 (Cytoscape) and not the page's own port; the
# R package prints what it uses, and both sides take the number as a setting.
DEFAULT_PORT = 8793
PATH = "/grownet/glv"
# where the companion package lives and how it is installed, in one place, so the page, the help and the
# error below say the same line
REPOSITORY_SLUG = "crossfeed-bio/crossfeed"
# What a reader of a release should run. The help ships with the tool, so it says what holds for the
# released version and never for the branch it was written on (Karoline, 2026-10-04: "The help should
# refer to the stage the tool is in when released"). Installing from an unmerged branch is a development
# step; it is in docs/agents/NOTES.md and in CONTRIBUTING.md, not here.
INSTALL_R = f'remotes::install_github("{REPOSITORY_SLUG}", subdir = "r")'
# Why an install can fail on a public repository: a GitHub token stored on the machine, for another
# account or scope, makes GitHub answer 404 instead of serving it anonymously. The way around it is a
# local install, which needs no GitHub access; clearing the token is not suggested, since that changes
# the session for everything else in it (Karoline, 2026-10-04: "I don't think we should recommend it for
# users, as it alters their system settings in ways that can affect them negatively").
INSTALL_TROUBLE = ('If that fails with "HTTP error 404", a GitHub token stored on this machine is being '
                   'used and cannot see the repository. Installing from a clone needs no GitHub access: '
                   'remotes::install_local("<the repository>/r"), or R CMD INSTALL r in a terminal.')



class RError(RuntimeError):
    """R could not be reached or refused the parameters, with what to do about it."""


# What can go wrong on the wire: urllib's own errors, http.client's for a listener that answers with
# something that is not HTTP, and the socket errors outside urllib's wrapping (as in `cytoscape`).
WIRE_ERRORS = (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError)


def base_url(port: int = DEFAULT_PORT) -> str:
    return f"http://127.0.0.1:{int(port)}"


def _local(url: str) -> str:
    """Every request goes to this machine, checked where the request is made."""
    if not url.startswith("http://127.0.0.1:"):
        raise RError(f"refusing to send to {url!r}: grownet only talks to an R session on this machine")
    return url


def send(payload: dict, port: int = DEFAULT_PORT, timeout: float = 30.0) -> dict:
    """POST the gLV payload to a listening R session and return what it answered.

    The answer is R's own: {"received": true, "organisms": n, "growth_rates": n, ...} from
    `grownet::grownet_listen`. Raises `RError` with what to do when nothing is listening or the
    listener is not the R package.
    """
    url = _local(f"{base_url(port)}{PATH}")
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:   # noqa: S310 - localhost only
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RError(f"the R session refused the parameters ({e.code} {e.reason}). Check that the grownet "
                     "package there is up to date.") from None
    except http.client.HTTPException as e:
        raise RError(f"something is listening on port {port}, but it did not answer the way the grownet R "
                     f"package does ({type(e).__name__}). Check which port grownet_listen() printed and "
                     "that no other program holds it.") from None
    except WIRE_ERRORS as e:
        raise RError(unreachable(port, getattr(e, "reason", e))) from None
    try:
        answer = json.loads(text) if text.strip() else {}
    except ValueError:
        raise RError(f"the listener on port {port} answered something that is not JSON, so it is not the "
                     "grownet R package") from None
    if not isinstance(answer, dict) or not answer.get("received"):
        raise RError(f"the listener on port {port} did not confirm the parameters: {text[:200]!r}")
    # an R package older than the payload reads no organisms out of it and still answers "received", so
    # the page said it had sent n organisms while the R session held an empty matrix (found 2026-10-06).
    # The check is here because this is the side that can be upgraded.
    sent = sum(len(block.get("organisms") or ()) for block in (payload.get("matrices") or ()))
    if sent and not answer.get("organisms"):
        # "send again" could not work on its own: the listener stops after one payload, so the reader
        # has to start it again before anything can arrive (#142 item 10)
        raise RError(f"the R session received the parameters and read no organisms out of them, so its "
                     f"grownet package is older than this one ({payload.get('format', 'the payload')}). "
                     'In R: remotes::install_github("crossfeed-bio/crossfeed", subdir = "r"), then '
                     'library(grownet) and grownet_listen() again, and send once that is waiting.')
    return answer


def unreachable(port: int = DEFAULT_PORT, reason: object = "") -> str:
    """What to do when nothing answers, worded for the page and for the command line."""
    detail = f" ({reason})" if reason else ""
    return (f"no R session is listening on port {port}{detail}. In R: "
            f"install.packages(\"remotes\"); {INSTALL_R}; library(grownet); glv <- grownet_listen(). "
            "Or fetch the same parameters from R without a listener, with grownet_glv(url), where url is "
            "the gLV address shown under this control.")
