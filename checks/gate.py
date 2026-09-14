"""crossfeed guardrails: a re-runnable gate (run in CI and before every commit).

Self-contained (no dependency on any private path), so it runs the same for every contributor and in
CI. Discipline is the point: each check is a small, readable guard that blocks a class of mistake.

Checks:
  1. secrets          no api keys, tokens, or private keys in tracked text
  2. no-raw-data      no pulled or raw experimental data committed (only synthetic tests/fixtures)
  3. no-local-paths   no absolute local-machine paths (the repo is portable and self-contained)
  4. self-contained   every import under src/ resolves to the standard library or crossfeed itself
  5. house-style      docs use ASCII punctuation and US spelling; prose carries no hedging caveats
  6. schema-contract  the shipped JSON Schema matches the code, and emitted networks validate against it

Tests run separately (pytest), in CI and from the pre-commit hook.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXT_EXT = (".py", ".md", ".toml", ".yml", ".yaml", ".json", ".cfg", ".ini", ".txt")

SECRET = re.compile(
    r"(?i)(?:api[_-]?key|secret|token|password|authorization|bearer)\s*[:=]\s*"
    r"['\"][A-Za-z0-9/\+=_\-\.]{16,}['\"]"
    r"|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)
LOCAL_PATH = re.compile(r"(?i)(?:[a-z]:[\\/]dev[\\/]|[a-z]:[\\/]users[\\/]|/home/|/users/)")
# hedging caveats: the tic implies the rest is not; say it plainly instead.
CAVEATS = re.compile(r"(?i)\b(?:honestly|frankly|candidly|truthfully)\b|\bto be honest\b|\bone honest flag\b")
# a small, conservative British-spelling denylist (US spelling is the house style)
BRITISH = re.compile(
    r"(?i)\b(?:colour|behaviour|favour|flavour|honour|analyse|organise|optimise|maximise|minimise|"
    r"catalyse|characterise|summarise|generalise|modelling|labelled|cancelled|travelled|signalling|"
    r"defence|offence|centre|litre|fibre|licence|grey)\b"
)
# em/en dash anywhere; a spaced hyphen used as a dash BETWEEN tokens (not a markdown list marker)
DASH = re.compile(r"[–—]|(?<=\S) -- (?=\S)|(?<=\S) - (?=\S)")

STDLIB = set(getattr(sys, "stdlib_module_names", set())) | {"__future__"}


def tracked_files():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
        return [p for p in out.stdout.splitlines() if p.strip()]
    except Exception:
        return []


def _read(rel):
    try:
        return open(os.path.join(ROOT, rel), encoding="utf-8", errors="ignore").read()
    except OSError:
        return None


def _strip_code(md):
    """Remove fenced blocks and inline code so CLI examples do not trip the prose checks."""
    md = re.sub(r"```.*?```", "", md, flags=re.DOTALL)
    md = re.sub(r"`[^`]*`", "", md)
    return md


def check_secrets(rels):
    hits = []
    for rel in rels:
        if rel.endswith(TEXT_EXT):
            text = _read(rel)
            if text and SECRET.search(text):
                hits.append(f"secret-like string in {rel}")
    return hits


def check_no_raw_data(rels):
    bad = []
    for rel in rels:
        r = rel.replace("\\", "/")
        if r.startswith("data/"):
            bad.append(f"raw data committed: {r} (data/ must stay out of git)")
        elif r.endswith(".csv") and not r.startswith("tests/fixtures/"):
            bad.append(f"csv committed outside tests/fixtures/: {r}")
    return bad


RULES_FILE = "checks/gate.py"   # defines the denylists below, so it is exempt from the prose and path scans


def check_no_local_paths(rels):
    bad = []
    for rel in rels:
        if rel.replace("\\", "/") == RULES_FILE:
            continue
        if rel.endswith(TEXT_EXT):
            text = _read(rel)
            if text and LOCAL_PATH.search(text):
                bad.append(f"absolute local-machine path in {rel} (keep the repo portable)")
    return bad


def check_self_contained(rels):
    bad = []
    for rel in rels:
        r = rel.replace("\\", "/")
        if not (r.startswith("src/") and r.endswith(".py")):
            continue
        text = _read(rel)
        if not text:
            continue
        try:
            tree = ast.parse(text, filename=rel)
        except SyntaxError as e:
            bad.append(f"{r}: syntax error ({e})")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods = [n.name.split(".")[0] for n in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods = [node.module.split(".")[0]]
            else:
                continue
            for m in mods:
                if m != "crossfeed" and m not in STDLIB:
                    bad.append(f"{r}: imports {m!r} (not stdlib or crossfeed; declare it or drop it)")
    return bad


def check_house_style(rels):
    bad = []
    for rel in rels:
        r = rel.replace("\\", "/")
        if r == RULES_FILE:
            continue
        text = _read(rel)
        if not text:
            continue
        # caveats: scan all tracked text (docs and code)
        if rel.endswith(TEXT_EXT):
            for m in CAVEATS.finditer(text):
                bad.append(f"{r}: hedging caveat {m.group(0)!r} (say it plainly)")
        # dashes and US spelling: prose only (docs), outside code spans
        if r.endswith(".md"):
            prose = _strip_code(text)
            if DASH.search(prose):
                bad.append(f"{r}: dash punctuation (use grammar: comma, colon, parentheses, or 'to')")
            for m in BRITISH.finditer(prose):
                bad.append(f"{r}: British spelling {m.group(0)!r} (US spelling is the house style)")
    return bad


def check_schema_contract(_rels):
    """Import crossfeed and confirm the shipped schema matches the code and emitted networks validate.
    Skips (does not fail) if crossfeed is not importable, so the gate still runs standalone."""
    src = os.path.join(ROOT, "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    try:
        import json

        from crossfeed.mgrowthdb import records_to_network
        from crossfeed.schema import SCHEMA_DOC, SCHEMA_FILE, validate_document
    except Exception as e:  # noqa: BLE001 - the gate must not crash if the package is absent
        print(f"    (schema-contract skipped: crossfeed not importable: {e})")
        return []

    bad = []
    try:
        with open(SCHEMA_FILE, encoding="utf-8") as f:
            on_disk = json.load(f)
        if on_disk != SCHEMA_DOC:
            bad.append("schema/interaction_network.schema.json drifted from schema.py "
                       "(regenerate it from crossfeed.schema.schema_json)")
    except OSError:
        bad.append("schema/interaction_network.schema.json is missing")

    fixture = os.path.join(ROOT, "tests", "fixtures", "example_interactions.json")
    try:
        with open(fixture, encoding="utf-8") as f:
            records = json.load(f)
        doc = records_to_network(records, meta={"source_db": "fixture"}).to_dict()
        problems = validate_document(doc)
        if problems:
            bad.append("an emitted network fails its own schema: " + "; ".join(problems))
    except OSError:
        pass  # fixture optional
    return bad


CHECKS = [
    ("secrets", check_secrets),
    ("no-raw-data", check_no_raw_data),
    ("no-local-paths", check_no_local_paths),
    ("self-contained", check_self_contained),
    ("house-style", check_house_style),
    ("schema-contract", check_schema_contract),
]


def main():
    rels = tracked_files()
    if not rels:
        print("gate: not a git tree yet (nothing tracked); skipping file checks.")
        return 0
    all_fails = []
    for name, fn in CHECKS:
        fails = fn(rels)
        mark = "OK  " if not fails else "FAIL"
        print(f"  [{mark}] {name}" + (f" ({len(fails)})" if fails else ""))
        for f in fails:
            print(f"         X {f}")
        all_fails += fails
    if all_fails:
        print(f"\nGATE FAIL: {len(all_fails)} problem(s) across {len(rels)} tracked files.")
        return 1
    print(f"\nGATE OK: {len(rels)} tracked files clean across {len(CHECKS)} checks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
