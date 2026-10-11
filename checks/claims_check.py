r"""FRONT-DOOR CLAIMS GUARD: the docs a stranger reads must agree with the code and with each other.

Why this exists (2026-09-21). Two claims went wrong in the same week, both in `README.md`, which is the
one file someone lands on first:

  * It described `BaselineDeriver` as the method after `ReplicateDeriver` had become the default, so the
    front door named a retired placeholder while the code ran something else.
  * It said a technique mismatch leaves "the direction of an interaction dependable while the magnitude
    is provisional". That was corrected in `docs/agents/NOTES.md` on 2026-09-18, because near the neutral
    band a cross-technique offset can move the sign too. The correction sat in the notes for three days
    while the README told visitors the opposite.

Neither is the kind of drift a person catches by rereading, and neither was caught by the existing gate:
`no-raw-data`, `house-style` and the rest check form, not claims. The schema-contract check proves the
model and the schema agree; nothing proved the prose agreed with either.

Two checks, both static:

  1. DEFAULT DERIVER. The deriver that `derive.derive_interactions` actually falls back to is read from
     the source, so this cannot go stale on its own. The docs must name that one as the default, and must
     never call a retired deriver the default.
  2. RETIRED CLAIMS. A claim that has been corrected may appear only alongside its correction, so the
     sentence that records the correction is allowed and a bare restatement is not.

Adding a corrected claim is one entry in RETIRED_CLAIMS: the wrong assertion, the marker that shows the
text is discussing the correction, and why it was retired.

Run: python checks/claims_check.py
Exit: 0 clean, 1 a claim disagrees with the code or with its own correction.
"""
from __future__ import annotations

import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The docs a reader meets before they read any code. `docs/LIMITATIONS.md` is here because it was not:
# when the default derivation changed, the one document whose whole job is to name the tool's weaknesses
# went on describing the other form's, and promising fields the shipped default never writes, while this
# gate passed (2026-10-10).
DOCS = ("README.md", "docs/METHOD_NOTES.md", "docs/agents/NOTES.md", "CONTRIBUTING.md",
        "docs/LIMITATIONS.md")

# Phrases that assert something is the current default, rather than mentioning it.
ASSERTS_DEFAULT = re.compile(
    r"is the default|as the default|the default for|default deriver|default derivation|"
    r"why it is the default|is still what|is what `?main`? runs|runs by default",
    re.I,
)
WINDOW = 200   # characters either side of a mention, for judging what a sentence is claiming

# (wrong assertion, marker showing the text is stating the correction, why it was retired)
RETIRED_CLAIMS = [
    (
        re.compile(r"direction\b[^.]{0,80}\bdependable\b", re.I),
        re.compile(r"not fully dependable|not dependable|sign can move|move the sign", re.I),
        "a technique mismatch was said to leave the direction dependable and only the magnitude "
        "provisional. Corrected 2026-09-18: near the neutral band a cross-technique offset can move the "
        "sign as well, so a mismatched edge's direction is not fully dependable either.",
    ),
    (
        re.compile(r"--include-neutral|neutral (and low-quality )?edges? (are|is) (computed|hidden|shown)", re.I),
        re.compile(r"absence of an edge|no .?neutral edge|not a .?neutral edge|absence threshold|replaces", re.I),
        "a comparison with no interaction was described as a neutral edge, hidden by default and shown with "
        "--include-neutral. Corrected 2026-09-21 (Karoline): a neutral edge is a contradiction; a comparison "
        "below the absence threshold k is the absence of an edge, exported with status absent.",
    ),
    (
        # an edge or a comparison asserted to carry Welch's test, said of networks in general. Narrow on
        # purpose: a historical note that says "a paired test instead of Welch" is not this claim.
        re.compile(r"(?:carries|carry|gets|get|is tested with|are tested with|tested with)\s+Welch", re.I),
        re.compile(r"specified comparison|replicate sets|meta\.statistics|its derivation|the derivation "
                   r"ran|which test|integrated form", re.I),
        "every network said in meta.statistics that it ran Welch's t-test on per-replicate log2 values, "
        "which is the specified comparison's test; the integrated form, the default since 2026-10-06, "
        "compares no replicate sets and runs a different test. Corrected 2026-10-07 (#142 item 5): a "
        "derivation states its own statistics and provisional note, and text that mentions Welch has to "
        "say which derivation runs it.",
    ),
]


def default_deriver() -> str:
    """The derivation the tool runs when the reader changes nothing, read from the code.

    Anchoring on the code rather than on a name written here is the point: a guard that carries its own
    copy of the answer goes stale in exactly the way it exists to prevent.

    The page's and the command line's default is `gui.DEFAULTS["derivation"]`, and `gui.chosen_deriver`
    turns it into a class; "replicate" means it builds none and `derive_interactions` falls back to its
    own, which is read below. Before 2026-10-06 the setting was "replicate", so that fallback was the
    whole answer.
    """
    gui = open(os.path.join(ROOT, "src", "grownet", "gui.py"), encoding="utf-8").read()
    chosen = re.search(r'"derivation":\s*"(\w+)"', gui)
    if chosen and chosen.group(1) != "replicate":
        wanted = chosen.group(1)
        for name in deriver_classes():
            if name.lower().startswith(wanted):
                return name
        raise SystemExit(f"claims-check: no deriver class matches the default derivation {wanted!r}")
    src = open(os.path.join(ROOT, "src", "grownet", "derive.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "derive_interactions"), None)
    if fn is None:
        raise SystemExit("claims-check: derive_interactions not found in src/grownet/derive.py")
    for node in ast.walk(fn):
        # the `deriver = deriver or SomeDeriver(...)` fallback
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            for value in node.values:
                if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) \
                        and value.func.id.endswith("Deriver"):
                    return value.func.id
    raise SystemExit("claims-check: no deriver fallback found in derive_interactions")


def deriver_classes() -> list:
    """Every deriver the project ships, wherever it lives: derive.py holds the specified comparison and
    the retired baseline, integrated.py the form that became the default on 2026-10-06."""
    out = []
    for module in ("derive.py", "integrated.py"):
        src = open(os.path.join(ROOT, "src", "grownet", module), encoding="utf-8").read()
        out += [n.name for n in ast.walk(ast.parse(src))
                if isinstance(n, ast.ClassDef) and n.name.endswith("Deriver") and n.name != "Deriver"]
    return out


def _read(rel: str) -> str:
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        return ""
    return open(path, encoding="utf-8").read().replace("\r\n", "\n")


def check_default_deriver(problems: list) -> None:
    """Whether the docs name the deriver the tool actually runs, and no longer name another one.

    A phrase is read as a claim about the **nearest** deriver named within `WINDOW`, not about every
    deriver in the window. Since 2026-10-10 the two have different jobs, so the sentence a reader needs
    is "A is the default, B is what gLV mode selects", and both names sit in one paragraph: attributing
    the phrase to every name in range made that correct sentence unwritable.
    """
    current = default_deriver()
    retired = [c for c in deriver_classes() if c != current]
    named_somewhere = False

    for rel in DOCS:
        text = _read(rel)
        if not text:
            continue
        # a claim can name the derivation by its class or by the flag a reader types; both are mentions,
        # because "**The default derivation.** `--derivation integrated`" names one without the class
        # and went unchecked while this read class names alone (2026-10-10)
        spellings = {cls: [cls] for cls in deriver_classes()}
        for cls in spellings:
            value = cls[:-len("Deriver")].lower() if cls.endswith("Deriver") else cls.lower()
            spellings[cls].append(f"--derivation {value}")
        mentions = [(m.start(), m.end(), cls) for cls, words in spellings.items()
                    for word in words for m in re.finditer(re.escape(word), text)]
        for claim in ASSERTS_DEFAULT.finditer(text):
            near = [(start, end, cls) for start, end, cls in mentions
                    if start - WINDOW <= claim.start() and claim.end() <= end + WINDOW]
            if not near:
                continue
            # the one whose name sits closest to the phrase is the one the phrase is about
            start, _end, cls = min(near, key=lambda x: min(abs(x[0] - claim.end()),
                                                           abs(claim.start() - x[1])))
            if cls == current:
                named_somewhere = True
            elif cls in retired:
                line = text[:start].count("\n") + 1
                problems.append(
                    f"{rel}:{line}: calls `{cls}` the default, but the tool runs `{current}` when "
                    f"the reader changes nothing. Say which one ships.")
    if not named_somewhere:
        problems.append(
            f"no doc in {', '.join(DOCS)} names `{current}` as the default, and it is what the tool "
            f"runs when the reader changes nothing. A reader cannot tell what the tool runs.")


VIEWER = "gui/index.html"
# Vocabularies the viewer has to understand to draw an edge correctly. Each is a tuple in model.py.
VOCABULARIES = ("QUALITY_FLAGS", "CAUTIONS", "EVIDENCE", "OUTCOMES")


def model_vocabulary(name: str) -> list:
    """The string values of a module-level tuple in model.py, read from the source."""
    src = open(os.path.join(ROOT, "src", "grownet", "model.py"), encoding="utf-8").read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Assign) and any(
                isinstance(tgt, ast.Name) and tgt.id == name for tgt in node.targets):
            if isinstance(node.value, (ast.Tuple, ast.List)):
                return [e.value for e in node.value.elts if isinstance(e, ast.Constant)
                        and isinstance(e.value, str)]
    return []


def check_viewer_knows_the_vocabulary(problems: list) -> None:
    """The viewer must name every flag the model can put on an edge.

    It has fallen behind three times: once when `evidence` arrived and an indirect arc drew as a direct
    one, once when `status` arrived and absent comparisons drew as interactions, and once when
    `single_replicate` changed from hidden to shown. Each time the model moved and nothing said so. A
    value the viewer does not name is a value it cannot be drawing correctly.
    """
    text = _read(VIEWER)
    if not text:
        return
    for name in VOCABULARIES:
        for value in model_vocabulary(name):
            if value not in text:
                problems.append(
                    f"{VIEWER}: model.{name} includes {value!r} and the viewer never names it, so it "
                    f"cannot be drawing or filtering it. Handle it, or say in a comment why it needs no "
                    f"treatment.")


def check_retired_claims(problems: list) -> None:
    for rel in DOCS:
        text = _read(rel)
        if not text:
            continue
        for claim, correction, why in RETIRED_CLAIMS:
            for m in claim.finditer(text):
                window = text[max(0, m.start() - WINDOW):m.end() + WINDOW]
                if correction.search(window):
                    continue          # the text is stating the correction, which is what we want
                line = text[:m.start()].count("\n") + 1
                problems.append(f"{rel}:{line}: retired claim {m.group(0)!r} restated without its "
                                f"correction. {why}")


def main() -> int:
    problems: list = []
    check_default_deriver(problems)
    check_retired_claims(problems)
    check_viewer_knows_the_vocabulary(problems)

    if problems:
        print("CLAIMS CHECK FAILED:")
        for p in problems:
            print(f"  {p}")
        return 1
    print(f"  [OK  ] claims: docs name `{default_deriver()}` as the default and restate no retired claim")
    return 0


if __name__ == "__main__":
    sys.exit(main())
