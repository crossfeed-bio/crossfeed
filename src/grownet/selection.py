"""Which experiments a search looks at: media, experiment ids, study ids (#113).

Karoline, 2026-10-04, weakening her earlier stance against environment filtering now that grownet exports
gLV parameters ("it's one thing to export a network of known interactions and another to do a gLV
simulation"): "a second, optional, input field next to the first one with the taxa. Users can either
specify names of media or a list of experiment identifiers there ... The media will have to be
string-matched against the experiment description; they are not systematically provided by mGrowthDB."

What the box takes, one entry per line, matched with OR:

  * an **experiment id** (`EMGDB000000031`) or a **study id** (`SMGDB00000004`), recognized by their shape;
  * anything else is a **medium**, matched case-insensitively as a substring.

A medium is matched against three things, because mGrowthDB spreads the environment over them. Every
experiment today does carry a structured `mediumName` on its compartments (559 of 559 when this was
written), so that is matched first; the spellings differ between studies though (Wilkins-Chalgren appears
four ways, one of them misspelled), which is why the match is a substring and not an equality. The
experiment's description and name are matched too, since what distinguishes experiments inside one study
lives only there: study 2 runs BT_WC and BT_MUCIN on one medium, study 4 runs +Ac and -Ac.

Selecting does not change how an interaction is derived. A comparison already never mixes media, because
the compartment record that carries the medium is part of the conditions two replicate sets must share
(`derive.conditions`). This is a way of looking at less, not a different method.
"""
from __future__ import annotations

import re

EXPERIMENT_ID = re.compile(r"(?i)^EMGDB\d+$")
STUDY_ID = re.compile(r"(?i)^SMGDB\d+$")

# what the page shows under the box, one of each kind it takes (the box itself starts empty)
EXAMPLES = ("Wilkins-Chalgren", "mucin", "SMGDB00000004", "EMGDB000000031")


def parse(entries) -> dict:
    """{"media", "experiments", "studies", "entries"} from the lines of the box.

    `entries` is a list of strings (or one string, split by `grownet.taxonomy.split_entries` first). Ids
    are kept uppercase, the way mGrowthDB writes them; a medium keeps the user's own spelling for the
    report and is matched case-insensitively.
    """
    if isinstance(entries, str):
        entries = entries.splitlines()
    from .taxonomy import split_entries
    entries = split_entries(entries)          # one per line, and at commas and semicolons, as the first box
    media, experiments, studies, kept = [], [], [], []
    for raw in entries:
        entry = raw.strip()
        if not entry:
            continue
        kept.append(entry)
        if EXPERIMENT_ID.match(entry):
            experiments.append(entry.upper())
        elif STUDY_ID.match(entry):
            studies.append(entry.upper())
        else:
            media.append(entry)
    return {"media": media, "experiments": experiments, "studies": studies, "entries": kept}


def empty(selection: dict | None) -> bool:
    """Whether a selection asks for anything at all."""
    return not selection or not (selection.get("media") or selection.get("experiments")
                                 or selection.get("studies"))


def medium_of(exp: dict) -> str:
    """The medium an experiment ran in, as mGrowthDB names it, or "" when it names none.

    One name per compartment, joined when a design has several, so a two-compartment experiment says both.
    """
    names = [(c.get("mediumName") or "").strip() for c in exp.get("compartments", [])]
    return "; ".join(dict.fromkeys(n for n in names if n))


def medium_url(exp: dict) -> str:
    """The reference mGrowthDB gives for that medium, when it gives one."""
    urls = [(c.get("mediumUrl") or "").strip() for c in exp.get("compartments", [])]
    return "; ".join(dict.fromkeys(u for u in urls if u))


def _text(exp: dict) -> str:
    """Where a medium is looked for: its name, the description, and the experiment's own name."""
    return " \n".join([medium_of(exp), exp.get("description") or "", exp.get("name") or ""]).casefold()


def matched_by(exp: dict, selection: dict) -> str:
    """The entry of the selection this experiment matches, or "" when none does.

    An id matches exactly; a medium matches as a case-insensitive substring of the medium name, the
    description or the experiment name.
    """
    if empty(selection):
        return ""
    exp_id = str(exp.get("id", "")).upper()
    if exp_id and exp_id in selection.get("experiments", ()):
        return exp_id
    study = str(exp.get("studyId", "")).upper()
    if study and study in selection.get("studies", ()):
        return study
    text = _text(exp)
    for medium in selection.get("media", ()):
        if medium.casefold() in text:
            return medium
    return ""


def matches(exp: dict, selection: dict) -> bool:
    return bool(matched_by(exp, selection))
