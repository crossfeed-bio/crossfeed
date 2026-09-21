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

# The docs a reader meets before they read any code.
DOCS = ("README.md", "docs/METHOD_NOTES.md", "docs/agents/NOTES.md", "CONTRIBUTING.md")

# Phrases that assert something is the current default, rather than mentioning it.
ASSERTS_DEFAULT = re.compile(
    r"is the default|as the default|the default for|default deriver|"
    r"is still what|is what `?main`? runs|runs by default",
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
]


def default_deriver() -> str:
    """The class `derive_interactions` falls back to, read from its source.

    Anchoring on the code rather than on a name written here is the point: a guard that carries its own
    copy of the answer goes stale in exactly the way it exists to prevent.
    """
    src = open(os.path.join(ROOT, "src", "crossfeed", "derive.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "derive_interactions"), None)
    if fn is None:
        raise SystemExit("claims-check: derive_interactions not found in src/crossfeed/derive.py")
    for node in ast.walk(fn):
        # the `deriver = deriver or SomeDeriver(...)` fallback
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
            for value in node.values:
                if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) \
                        and value.func.id.endswith("Deriver"):
                    return value.func.id
    raise SystemExit("claims-check: no deriver fallback found in derive_interactions")


def deriver_classes() -> list:
    src = open(os.path.join(ROOT, "src", "crossfeed", "derive.py"), encoding="utf-8").read()
    return [n.name for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.ClassDef) and n.name.endswith("Deriver") and n.name != "Deriver"]


def _read(rel: str) -> str:
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        return ""
    return open(path, encoding="utf-8").read().replace("\r\n", "\n")


def check_default_deriver(problems: list) -> None:
    current = default_deriver()
    retired = [c for c in deriver_classes() if c != current]
    named_somewhere = False

    for rel in DOCS:
        text = _read(rel)
        if not text:
            continue
        for cls in deriver_classes():
            for m in re.finditer(re.escape(cls), text):
                window = text[max(0, m.start() - WINDOW):m.end() + WINDOW]
                if not ASSERTS_DEFAULT.search(window):
                    continue
                line = text[:m.start()].count("\n") + 1
                if cls == current:
                    named_somewhere = True
                elif cls in retired:
                    problems.append(
                        f"{rel}:{line}: calls `{cls}` the default, but `derive_interactions` falls back "
                        f"to `{current}`. Say which one ships.")
    if not named_somewhere:
        problems.append(
            f"no doc in {', '.join(DOCS)} names `{current}` as the default, and it is what "
            f"`derive_interactions` falls back to. A reader cannot tell what the tool runs.")


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

    if problems:
        print("CLAIMS CHECK FAILED:")
        for p in problems:
            print(f"  {p}")
        return 1
    print(f"  [OK  ] claims: docs name `{default_deriver()}` as the default and restate no retired claim")
    return 0


if __name__ == "__main__":
    sys.exit(main())
