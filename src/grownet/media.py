"""What makes two experiments the same medium (#142, from Karoline's decision of 2026-10-07).

Karoline, closing the open decision on #141: "capacity merge by medium is a good idea. in addition, we can
do the stricter test that foodnet does; medium matches but contradicting extras, such as acetic acid or
mucin, do not count as matching medium." And on applying it beyond that merge: "foodnet's strict medium
rule should be applied in general in case someone specifies it in the 2nd search box (because such changes
alter interactions); and it should also be documented."

mGrowthDB names a medium per compartment and does not report its composition systematically: an added
sugar, a removed carbon source or a supplement usually lives only in the experiment's description or name
("WC plus mucin beads", "RI_BH -Ac", "supplemented with 2g/L trehalose"). Matching on the medium name
alone therefore puts different media together. Measured on the live database (2026-10-07, all 559
experiments): the names alone give 15 media, and this rule gives 60.

A medium's identity (`identity`) is:

  * the medium names of its compartments, without case, punctuation or a parenthesized abbreviation, so
    "Wilkins-Chalgren Anaerobe Broth (WC)" and "Wilkins-Chalgren Anaerobe Broth" are one medium, and a
    two-compartment design keeps both names (`base_key`);
  * every alteration the description states (`alterations`): something added ("plus", "supplemented with",
    "+X", "X added", an amount such as "1 mM galactose") or taken away ("without", "with no", "X-free",
    "instead of X"), with its amount where one is stated, since 0.1 and 0.75 percent linoleic acid are two
    media;
  * the atmosphere where it is recorded (`atmosphere`): the gas composition of the compartments. An
    experiment that records none is not taken as different; it joins the recorded variant of its medium
    (`assign_atmospheres`).

This rule is foodnet's (`src/foodnet/media.py` in hallucigenia-sparsa/foodnet, the sister tool), with one
adaptation grownet needs. **foodnet also reads "+X" and "-X" in an experiment's name, and grownet must
not.** foodnet's own module says that is safe because foodnet reads monocultures; grownet reads
co-cultures, where those forms name community members: `At+Ct`, `At+Ms`, `Ct+Ms` in SMGDB00000013 and
`LB+STneg`, `LB+STpos` in SMGDB00000006. With the name patterns on, those two studies split into 4 and 3
media that do not exist. With the description patterns alone they are one medium each, and every real
split survives: SMGDB00000014 into 12 (the linoleic and oleic acid series, TBHQ, DMSO), SMGDB00000026
into 17, SMGDB00000025 into 12, SMGDB00000019 into 5, SMGDB00000015 and SMGDB00000002 into 2, and
SMGDB00000004 into 3.

Each pattern below was written against the descriptions mGrowthDB holds and `tests/test_media.py` holds
those phrasings as cases. A phrasing nobody has used yet will not be recognized: the report lists every
medium a search found, so a reader can see what was told apart, and the second box takes an experiment id
for anything this rule gets wrong.
"""
from __future__ import annotations

import re

# words that follow an alteration but do not name the compound
_TRAILING = re.compile(r"\b(?:beads?|added|supplied|for \d.*|as .*|in .*|at \d.*|mixed .*)$")
_STOP = {"wc", "medium", "media", "broth", "the", "a", "an"}
_COMPOUND = r"(?P<compound>[a-z0-9][a-z0-9 \-()/'.%µμ]*?)"
# a compound ends at a sentence end (not a decimal point), a comma, or a word that starts what follows
_END = r"(?=\.(?!\d)|[;,]|\bfor\b|\bas\b|\bin\b|\bstarting\b|\busing\b|\bused\b|\binstead\b|$)"
_UNIT = r"(?:mm|mmol|g/l|g l-1|mg/l|mg/ml|%|um|µm|μm)"
_AMOUNT_TEXT = r"\d+(?:\.\d+)?\s*" + _UNIT + r"\s+(?:of\s+)?"
_AMOUNT = r"(?P<amount>" + _AMOUNT_TEXT + ")"

ADDED = [
    re.compile(r"\bplus\s+" + _AMOUNT + "?" + _COMPOUND + _END),
    re.compile(r"\bsupplemented with\s+" + _AMOUNT + "?" + _COMPOUND + _END),
    re.compile(r"\bwith (?:initial|added|additional)\s+" + _AMOUNT + "?" + _COMPOUND + _END),
    re.compile(r"\b(?:and|with)\s+" + _AMOUNT + _COMPOUND + _END),
    re.compile(r"\benriched with\s+" + _COMPOUND + _END),
    re.compile(r"\bspiked with\s+" + _COMPOUND + _END),
    # "0.1mg/L pantothenate added in the culture" (SMGDB00000019)
    re.compile(r"(?:^|[\s(])" + _AMOUNT + _COMPOUND + r"\s+(?:added|supplied)\b"),
    # "WC + 10 mM acetate"
    re.compile(r"\+\s*" + _AMOUNT + _COMPOUND + _END),
    # "20 mM fructose instead of glucose": the fructose is added, the glucose taken away (below)
    re.compile(r"(?:^|[\s(])" + _AMOUNT + _COMPOUND + r"\s+instead of\b"),
]
REMOVED = [
    re.compile(r"\bwithout (?:initial |added |additional )?" + _COMPOUND + r"(?=\bplus\b|" + _END[3:]),
    re.compile(r"\bwith no (?:additional |added )?" + _COMPOUND + _END),
    # "No supplied pantothenate in culture" (SMGDB00000019)
    re.compile(r"\bno (?:supplied|added|additional)\s+" + _COMPOUND + _END),
    re.compile(r"\blacking\s+" + _COMPOUND + _END),
    re.compile(r"\bdepleted of\s+" + _COMPOUND + _END),
    re.compile(r"\binstead of\s+" + _COMPOUND + _END),
    # "glucose-free WC"
    re.compile(r"\b(?P<compound>[a-z][a-z0-9\-]*?)-free\b"),
]


def _amount(text: str) -> str:
    """An amount as one spelling: "1 mM ", "1mM" and "1.0 mM" are "1mm"; "5 g l-1" is "5g/l"; the micro
    sign and the Greek mu are one."""
    if not text:
        return ""
    text = re.sub(r"\s+of\s*$", "", text.strip())
    found = re.match(r"(\d+(?:\.\d+)?)\s*(.*)$", text)
    if not found:
        return re.sub(r"\s+", "", text)
    number = float(found.group(1))
    unit = re.sub(r"\s+", "", found.group(2)).replace("gl-1", "g/l").replace("μ", "µ")
    # one unit per kind, so 5000 mg/L and 5 g/L are one medium, as are 1000 uM and 1 mM
    factor, unit = {"mg/l": (1e-3, "g/l"), "mg/ml": (1.0, "g/l"), "um": (1e-3, "mm"),
                    "µm": (1e-3, "mm"), "mmol": (1.0, "mm")}.get(unit, (1.0, unit))
    return f"{number * factor:g}{unit}"


def _clean(text: str) -> tuple:
    """(amount, compound) of one listed part: "1.5 µm tbhq antioxidant (dissolved in dmso)" is
    ("1.5µm", "tbhq antioxidant"); a remark in parentheses is not the compound."""
    text = re.sub(r"\([^)]*\)", " ", text).split("(")[0].strip()
    amount = ""
    found = re.match(r"^\s*(" + _AMOUNT_TEXT + ")", text)
    if found:
        amount, text = _amount(found.group(1)), text[found.end():]
    text = _TRAILING.sub("", " ".join(text.split()).strip(" ,"))
    words = [w for w in re.split(r"[\s,]+", text) if w and w not in _STOP]
    return amount, " ".join(words)


def _tokens(sign: str, match) -> set:
    found = set()
    groups = match.groupdict()
    amount = _amount(groups.get("amount"))
    for i, part in enumerate(re.split(r"\s+and\s+|,", match.group("compound"))):
        own, name = _clean(part)
        if name:
            # an amount is part of the medium: 0.1 and 0.75 percent linoleic acid are two media
            # (SMGDB00000014), as are 0.1 and 3.0 mg/L pantothenate (SMGDB00000019)
            dose = own or (amount if i == 0 else "")
            found.add(sign + (f"{dose} " if dose else "") + name)
    return found


def alterations(exp: dict) -> tuple:
    """The alterations an experiment's description states, as sorted tokens ("+mucin", "-glucose",
    "+1mm galactose").

    The description only. An experiment's **name** is not read, because in grownet "+X" names a
    co-culture member and not a supplement: see the note at the top of this module.
    """
    found = set()
    description = " ".join((exp.get("description") or "").casefold().split())
    for pattern in ADDED:
        for m in pattern.finditer(description):
            found |= _tokens("+", m)
    for pattern in REMOVED:
        for m in pattern.finditer(description):
            found |= _tokens("-", m)
    return tuple(sorted(t for t in found if len(t) > 1))


def _normalize(name: str) -> str:
    """One medium name reduced to its words: case, punctuation and a parenthesized abbreviation go."""
    text = re.sub(r"\([^)]*\)", " ", (name or "").casefold())
    return " ".join(re.sub(r"[^0-9a-z]+", " ", text).split())


def _token_key(changed) -> str:
    """The alteration tokens as the key spells them: spaces and hyphens inside a compound's name do not
    make another medium ("N-acetyl glucosamine")."""
    tokens = sorted({t[0] + re.sub(r"[\s\-]+", "", t[1:]) for t in changed})
    return "" if not tokens else " | " + " ".join(tokens)


def key_from_label(label: str) -> str:
    """The key of a medium given only the `label` an arc or a run recorded, not the experiment.

    A network carries the label, so two media already measured have to be comparable from it alone: this
    reverses `identity`'s label, whose alteration tokens always begin with "+" or "-" and sit in one
    parenthesis at the end. "" for an empty label, which matches nothing.
    """
    text = (label or "").strip()
    if not text:
        return ""
    changed: tuple = ()
    found = re.search(r"\s\(([+-][^()]*)\)$", text)
    if found:
        changed = tuple(part for part in (p.strip() for p in found.group(1).split(",")) if len(part) > 1)
        text = text[:found.start()]
    names = sorted({n for n in (_normalize(part) for part in text.split(";")) if n})
    return ("; ".join(names) or "unnamed medium") + _token_key(changed)


def base_key(exp: dict) -> str:
    """The compartments' medium names, reduced to what tells media apart.

    Case, punctuation and a parenthesized abbreviation go, so the four live spellings of Wilkins-Chalgren
    Anaerobe Broth reduce to one key where they say the same words. The names of a design's compartments
    are all kept, sorted, so a two-compartment experiment is not the same medium as either compartment on
    its own, which the old substring rule got wrong (#142 item 13).
    """
    parts = [_normalize(c.get("mediumName") or "") for c in exp.get("compartments", [])]
    return "; ".join(sorted({p for p in parts if p})) or "unnamed medium"


GASES = ("O2", "CO2", "H2", "N2")


def atmosphere(exp: dict) -> str:
    """The recorded gas composition ("CO2 10, H2 10, N2 80"), or "" when no compartment records one."""
    parts = []
    for c in exp.get("compartments", []):
        values = [(g, c.get(g)) for g in GASES if c.get(g) not in (None, "")]
        if values:
            parts.append(", ".join(f"{g} {float(v):g}" for g, v in values if float(v) > 0)
                         or "no gas recorded")
    return "; ".join(sorted(set(parts)))


def identity(exp: dict, strict: bool = True) -> dict:
    """{"key", "label", "alterations", "atmosphere"}: the medium an experiment ran in.

    `key` groups experiments into media and is what two media are compared by; `label` is what a reader
    sees, the medium's own name with its alterations. With `strict` False only the names count, which is
    what every medium comparison did before 0.3.0.
    """
    from .selection import medium_of
    name = medium_of(exp) or "unnamed medium"
    if not strict:
        return {"key": base_key(exp), "label": name, "alterations": (), "atmosphere": ""}
    changed = alterations(exp)
    key = base_key(exp) + _token_key(changed)
    label = name + ("" if not changed else " (" + ", ".join(changed) + ")")
    return {"key": key, "label": label, "alterations": changed, "atmosphere": atmosphere(exp)}


def assign_atmospheres(identities: list) -> list:
    """The final keys and labels for a list of `identity` results: experiments of one medium that record
    different atmospheres become different media; one that records none joins the most common recorded
    variant of its medium (or stays as it is when there is none)."""
    variants: dict = {}
    for ident in identities:
        if ident["atmosphere"]:
            counts = variants.setdefault(ident["key"], {})
            counts[ident["atmosphere"]] = counts.get(ident["atmosphere"], 0) + 1
    out = []
    for ident in identities:
        counts = variants.get(ident["key"], {})
        if len(counts) <= 1:
            out.append(ident)          # one atmosphere, or none recorded: the medium is not split
            continue
        gas = ident["atmosphere"] or max(sorted(counts), key=lambda g: counts[g])
        out.append({**ident, "key": f"{ident['key']} | {gas}", "label": f"{ident['label']} [{gas}]"})
    return out


def near_miss(one: str, other: str):
    """(word in the first, word in the second) where two media differ only in the spelling of one word,
    or None.

    What this is for: `steady.check` has to say why a chemostat was not scored, and "a coefficient is
    specific to its environment" is a scientific reason for what is sometimes a typo in a third-party
    database (Craig's agent, on #141). mGrowthDB holds "Wilkins-Chalgren An**a**erobe Broth" and
    "Wilkins-Chalgren An**e**robe Broth", two real studies and one medium. grownet does not merge them,
    since a character substitution says two names disagree rather than that one is less complete, but it
    can name the near miss instead of claiming the environments differ.
    """
    first, second = key_from_label(one), key_from_label(other)
    if not first or not second or first == second:
        return None
    base_one, _, changed_one = first.partition(" | ")
    base_two, _, changed_two = second.partition(" | ")
    if changed_one != changed_two:
        return None               # something was added or taken away: a real difference, not a spelling
    words_one, words_two = base_one.split(), base_two.split()
    if len(words_one) != len(words_two):
        return None
    differ = [(a, c) for a, c in zip(words_one, words_two, strict=True) if a != c]
    return differ[0] if len(differ) == 1 else None


def same_medium(one: dict, other: dict, strict: bool = True) -> bool:
    """Whether two experiments ran in the same medium, by `identity`'s key."""
    return identity(one, strict)["key"] == identity(other, strict)["key"]
