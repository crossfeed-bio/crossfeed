"""grownet guardrails: a re-runnable gate (run in CI and before every commit).

Self-contained (no dependency on any private path), so it runs the same for every contributor and in
CI. Discipline is the point: each check is a small, readable guard that blocks a class of mistake.

Checks:
  1. secrets          no api keys, tokens, or private keys in tracked text
  2. no-raw-data      no pulled or raw experimental data committed (only synthetic tests/fixtures)
  3. no-local-paths   no absolute local-machine paths (the repo is portable and self-contained)
  4. self-contained   every import under src/ resolves to the standard library or grownet itself
  5. house-style      docs use ASCII punctuation and US spelling; prose carries no hedging caveats
  6. schema-contract  the shipped JSON Schema matches the code, and an emitted network passes the
                     dependency-free validator (which is a SUBSET of that schema: see schema.py)
  7. claims          the docs a stranger reads name the deriver the code actually defaults to, and do not
                     restate a claim that has been corrected (see checks/claims_check.py)
  8. merge-markers    no leftover conflict markers from a merge (one once reached the changelog unseen)

Tests run separately (pytest), in CI and from the pre-commit hook.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A quoted value was required until 2026-10-11, so an unquoted one passed: `TOKEN: ghp_...` in a
# workflow `env:` block, or `TOKEN=...` in any scanned file, is how a real secret is most likely written
# here and is exactly what the quotes excluded. The quotes are optional now, and `bearer` may be followed
# by whitespace rather than a separator, which is how an Authorization header is written. A value must
# still be 16 or more characters from the class, so `${{ secrets.X }}`, `$VAR`, `<your-token>` and `""`
# do not match: a placeholder either starts outside the class or is too short.
# The whitespace-only separator is for `authorization` and `bearer` ALONE, which is how an Authorization
# header is written. Applied to all seven keywords it flagged ordinary prose, because one hyphenated word
# after "secret" or "token" is 16 characters of the class: "GitHub secret scanning-and-rotation", "the
# token docs/METHOD_NOTES.md describes", "a password manager.Keychain entry". In a project whose house
# style is long prose Markdown with inline file paths that blocks a commit, and a gate someone turns off
# is worse than none. The key header is broad enough for the forms openssl and gpg actually emit: DSA,
# ENCRYPTED and PGP PRIVATE KEY BLOCK were missed while the check's own description says "private keys".
SECRET = re.compile(
    r"(?i)(?:api[_-]?key|secret|token|password)\s*[:=]\s*"
    r"['\"]?[A-Za-z0-9/\+=_\-\.]{16,}['\"]?"
    r"|(?:authorization|bearer)\s*(?:[:=]\s*|\s+)"
    r"['\"]?[A-Za-z0-9/\+=_\-\.]{16,}['\"]?"
    r"|-----BEGIN [A-Z0-9 ]{0,20}PRIVATE KEY",
    re.I,
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

# a conflict's opening or closing line; a bare ======= alone is left alone (a Markdown heading underline)
MERGE_MARKER = re.compile(r"^(?:<{7}|>{7})(?: |$)", re.M)

STDLIB = set(getattr(sys, "stdlib_module_names", set())) | {"__future__"}


def tracked_files():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
        return [p for p in out.stdout.splitlines() if p.strip()]
    except Exception:
        return []


def _text_of(rel):
    """This file's content when it looks like text, else None: what the content checks scan.

    The nine-extension list missed 30 of 138 tracked files: 9 `.Rd`, 8 `.R`, the extensionless `LICENSE`,
    `NOTICE`, `Makefile`, `r/NAMESPACE` and `r/DESCRIPTION`, both `.svg`, and one each of `.gitignore`,
    `.cff`, `.in`, `.html`, `.Rbuildignore` and `.DS_Store`. The largest was `gui/index.html` at 52,570
    bytes, which is the whole viewer. Its failure mode is the one nobody can enumerate, the next
    extension no one thought of, and it had already cost two misses in four days: the `.sh` of this
    branch's own draft, and `schema/format_fields.json` on 2026-10-08 (Craig's agent measured #227).

    A NUL byte is the binary test, not UTF-8 decodability: a latin-1 or UTF-16 file fails a decode test
    while still being text a secret can sit in. The failure direction is the safe one, because a binary
    with no early NUL is scanned as text and yields a false positive rather than a silent miss. This is a
    better trade and not total coverage: it still skips whatever it judges binary, and the summary names
    those files, so the remaining miss is one anybody can enumerate.

    It goes through `_read` rather than opening the file itself, so one seam decides what every check
    sees. A version that read the disk directly made every test that supplies its files through `_read`
    scan nothing at all, silently, which is the shape of defect this gate exists to catch.
    """
    text = _read(rel)
    if text is None:
        return None
    return None if "\0" in text[:8192] else text


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
        text = _text_of(rel)
        if text and SECRET.search(text):
            hits.append(f"secret-like string in {rel}")
    return hits


# data-shaped files this large outside the allowed dirs are almost certainly a pulled or raw dump; the
# synthetic fixtures and the schema are tiny, so a low cap catches a data commit without blocking them.
DATA_EXT = (".json", ".tsv", ".txt", ".xml", ".parquet", ".h5", ".hdf5", ".xlsx", ".ndjson")
DATA_OK_PREFIXES = ("tests/fixtures/", "schema/")
DATA_MAX_BYTES = 50 * 1024


def check_no_raw_data(rels):
    bad = []
    for rel in rels:
        r = rel.replace("\\", "/")
        if r.startswith("data/"):
            bad.append(f"raw data committed: {r} (data/ must stay out of git)")
            continue
        if r.endswith(".csv") and not r.startswith("tests/fixtures/"):
            bad.append(f"csv committed outside tests/fixtures/: {r}")
            continue
        if r.endswith(DATA_EXT) and not r.startswith(DATA_OK_PREFIXES):
            try:
                size = os.path.getsize(os.path.join(ROOT, rel))
            except OSError:
                size = 0
            if size > DATA_MAX_BYTES:
                bad.append(f"large data-shaped file outside tests/fixtures/: {r} ({size // 1024} KB); "
                           "pulled or raw data must not be committed (data governance)")
    return bad


RULES_FILE = "checks/gate.py"   # defines the denylists below, so it is exempt from the prose and path scans


def check_no_local_paths(rels):
    bad = []
    for rel in rels:
        if rel.replace("\\", "/") == RULES_FILE:
            continue
        text = _text_of(rel)
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
                if m != "grownet" and m not in STDLIB:
                    bad.append(f"{r}: imports {m!r} (not stdlib or grownet; declare it or drop it)")
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
        if _text_of(rel):
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
    """Import grownet and confirm the shipped schema matches the code, and that an emitted network
    passes `validate_document`.

    **That is not the same as validating against the shipped JSON Schema**, and these three lines said it
    was. `validate_document` checks the enums, the required fields, a negative weight and referential
    integrity, and checks no numeric type, no `minimum`, no `maximum` and no string type: a hand-written
    network passes it and fails the schema nine ways. No emitted network violates the schema today, which
    was measured, so this was a false claim about a guard rather than a wrong output, and the honest fix
    is to say which validator runs (#249). Walking `SCHEMA_DOC`'s own keywords over the document here is
    the version that would make the original claim true, and both are in hand at this point.
    Skips (does not fail) if grownet is not importable, so the gate still runs standalone."""
    src = os.path.join(ROOT, "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    try:
        import json

        from grownet.mgrowthdb import records_to_network
        from grownet.schema import SCHEMA_DOC, SCHEMA_FILE, validate_document
    except Exception as e:  # noqa: BLE001 - the gate must not crash if the package is absent
        print(f"    (schema-contract skipped: grownet not importable: {e})")
        return []

    bad = []
    try:
        with open(SCHEMA_FILE, encoding="utf-8") as f:
            on_disk = json.load(f)
        if on_disk != SCHEMA_DOC:
            bad.append("schema/interaction_network.schema.json drifted from schema.py "
                       "(regenerate it from grownet.schema.schema_json)")
    except OSError:
        bad.append("schema/interaction_network.schema.json is missing")

    fixture = os.path.join(ROOT, "tests", "fixtures", "example_interactions.json")
    try:
        with open(fixture, encoding="utf-8") as f:
            records = json.load(f)
        doc = records_to_network(records, meta={"source_db": "fixture"}).to_dict()
        problems = validate_document(doc)
        if problems:
            bad.append("an emitted network fails the dependency-free validator: " + "; ".join(problems))
    except OSError:
        pass  # fixture optional
    return bad


def check_format_fields(_rels):
    """Refuse a change to a record's declared fields that the format manifest does not match.

    Craig's agent on #154, after #121 added optional arc fields under an unchanged format id and the
    daily artifact reached installed readers that could not build them: "commit a manifest of the
    format's declared fields, and have `checks/gate.py` fail when the live `Edge`, `Node` or `Study`
    fields differ from the manifest while `SCHEMA` is unchanged. Updating the manifest then becomes the
    deliberate act that makes a format change visible in review, and it would have stopped #121 at the
    gate rather than four days downstream."

    The manifest records a field set per format id, so the only ways to pass after adding a field are to
    take it back out, or to move `SCHEMA` and record the new id's set. Editing the entry of an id that
    has already shipped is possible and is meant to be: it rewrites what a released format carried, and
    it shows up as exactly that in review.

    Skips rather than fails when grownet is not importable, as the other import-dependent check does.
    """
    src = os.path.join(ROOT, "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    try:
        import json
        from dataclasses import fields

        from grownet.model import SCHEMA, Edge, Node, Study
    except Exception as e:  # noqa: BLE001 - the gate must not crash if the package is absent
        print(f"    (format-fields skipped: grownet not importable: {e})")
        return []

    path = os.path.join(ROOT, "schema", "format_fields.json")
    try:
        with open(path, encoding="utf-8") as f:
            manifest = json.load(f)
    except OSError:
        return ["schema/format_fields.json is missing: it records the fields each format id declares"]

    bad = []
    # This check reads the LIVE dataclasses, which is what makes it meaningful and also means its verdict
    # can be served from a stale `.pyc`, and the stale direction is a PASS. CPython invalidates bytecode
    # on (source mtime in whole seconds, source size), and two format ids of the same length are the same
    # size, so editing an id and reverting it inside one second leaves bytecode CPython considers current:
    # a developer who runs the gate, sees it fail, reverts and runs it again. CI is safe, since a fresh
    # clone has no `__pycache__`, and the exposure is exactly the local run, where this guard is worth
    # most. So the id is read out of the source as text and compared with the imported one, which turns a
    # silent false pass into a loud failure (Craig's agent, #168, having hit it by accident while testing
    # this check against the #121 mistake on the released head).
    in_source = re.search(r'^SCHEMA\s*(?::[^=]+)?=\s*["\'](?P<id>[^"\']+)["\']',
                          _read("src/grownet/model.py") or "", re.M)
    if in_source is None:
        # the guard above cannot guard itself: with no id read out of the source there is nothing to
        # compare the import against, and the old code then skipped the staleness test silently, which
        # is the failure it exists to prevent. An annotation or a wrapped line is enough to do it:
        # `SCHEMA: Final = "..."` imports fine and no longer matches a bare `^SCHEMA =`. So the check
        # refuses instead, the way `email_link_check` refuses a file whose body it cannot recognize
        # rather than passing it (Craig's agent on #176).
        return bad + ["this check could not find the SCHEMA declaration in src/grownet/model.py, so it "
                      "cannot tell whether the imported module is the code on disk and every verdict "
                      "below it would be unverified. Keep the declaration as a single assignment of a "
                      "literal, or widen the pattern in checks/gate.py to match the new form"]
    if in_source.group("id") != SCHEMA:
        # and nothing else is reported, because nothing else can be trusted: every verdict below comes
        # from the same import, including the field comparison that is this check's actual job and the
        # thing that catches the #121 mistake. Reporting them anyway produced a line that said
        # "model.py says /v3" while model.py said /v2 on disk, and prescribed moving the manifest's
        # `current` to an id the source does not contain, which is the line a developer acts on (Craig's
        # agent on #176, having reproduced the stale import against the real mechanism)
        return bad + [f"src/grownet/model.py says SCHEMA is {in_source.group('id')!r} and the imported "
                      f"module says {SCHEMA!r}: your bytecode is stale, so this check is reading code "
                      "that is no longer on disk and its verdict means nothing. Remove the __pycache__ "
                      "directories under src/grownet and run the gate again"]
    if manifest.get("current") != SCHEMA:
        bad.append(f"schema/format_fields.json says the current format is "
                   f"{manifest.get('current')!r} and model.py says {SCHEMA!r}: set `current` to the id "
                   "the code writes, and give that id its own entry under `formats`")
    recorded = (manifest.get("formats") or {}).get(SCHEMA)
    if recorded is None:
        return bad + [f"schema/format_fields.json has no entry for {SCHEMA!r}. Moving the format id is "
                      "how a field addition reaches a reader safely, so record what the new id declares"]
    live = {"edge": Edge, "node": Node, "study": Study}
    for kind, cls in live.items():
        here = sorted(f.name for f in fields(cls))
        there = sorted(recorded.get(kind) or [])
        added, gone = sorted(set(here) - set(there)), sorted(set(there) - set(here))
        if added:
            bad.append(f"{cls.__name__} declares {', '.join(added)}, which {SCHEMA} does not. A reader "
                       "of this format builds each record from every field a document carries, so a new "
                       "field reaches an installed copy as an error: move SCHEMA to a new id and record "
                       "that id's fields in schema/format_fields.json")
        if gone:
            bad.append(f"{SCHEMA} records {', '.join(gone)} for {cls.__name__} and the code no longer "
                       "declares them: removing a field from a format that has shipped is a breaking "
                       "change, so move SCHEMA to a new id rather than editing this one's entry")
    return bad


def check_claims(_rels):
    """Delegate to checks/claims_check.py: the docs a stranger reads agree with the code and with each
    other. Kept in its own file because its retired-claim list grows as claims are corrected, and that
    list is worth reading on its own."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import claims_check
    problems = []
    claims_check.check_default_deriver(problems)
    claims_check.check_retired_claims(problems)
    claims_check.check_viewer_knows_the_vocabulary(problems)
    return problems


def check_shadowed_definitions(rels):
    """A definition or a mapping key written twice in one file, where the language keeps only the last.

    This is the failure a merge leaves and NOTHING else catches. Resolving thirteen branches on
    2026-10-11, a keep-both-sides resolution gave one dict two `"outcome"` keys: Python silently keeps
    the last, so one branch's wording was lost, the file parsed, every test passed and the gate was
    clean. The same shape took two test FUNCTIONS out of a file in the same session, and a test that no
    longer exists cannot fail.

    Craig's agent extended it to JSON, where a duplicate key is also last-wins in every parser either
    side uses and where `schema/` and the fixtures live, and ran it over the merged tree before this
    existed. It found nothing then, which is the right time to add a check rather than the wrong one.

    Reported as a problem and not a note, because unlike an unknown field there is no reading under which
    a shadowed definition is intended.
    """
    import collections

    bad = []
    for rel in rels:
        r = rel.replace("\\", "/")
        text = _text_of(rel)
        if not text:
            continue
        if r.endswith(".py"):
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue            # ruff reports a syntax error; this check is about what parses
            for node in ast.walk(tree):
                if isinstance(node, ast.Dict):
                    keys = [k.value for k in node.keys
                            if isinstance(k, ast.Constant) and isinstance(k.value, str)]
                    for key, n in collections.Counter(keys).items():
                        if n > 1:
                            bad.append(f"{r}: dict key {key!r} written {n} times in one literal, and "
                                       "Python keeps only the last")
            top = [n.name for n in tree.body
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
            for name, n in collections.Counter(top).items():
                if n > 1:
                    bad.append(f"{r}: {name} defined {n} times at the top level, and Python keeps only "
                               "the last")
        elif r.endswith(".json"):
            def twice(pairs, rel=r):
                seen = collections.Counter(k for k, _ in pairs)
                for key, n in seen.items():
                    if n > 1:
                        bad.append(f"{rel}: JSON key {key!r} written {n} times in one object, and every "
                                   "parser keeps only the last")
                return dict(pairs)
            try:
                json.loads(text, object_pairs_hook=twice)
            except ValueError:
                continue            # an unparseable JSON file is not this check's business
    return bad


def check_merge_markers(rels):
    bad = []
    for rel in rels:
        text = _text_of(rel)
        for m in MERGE_MARKER.finditer(text or ""):
            bad.append(f"conflict marker left from a merge in {rel}, line {text.count(chr(10), 0, m.start()) + 1}")
    return bad


CHECKS = [
    ("secrets", check_secrets),
    ("no-raw-data", check_no_raw_data),
    ("no-local-paths", check_no_local_paths),
    ("self-contained", check_self_contained),
    ("house-style", check_house_style),
    ("schema-contract", check_schema_contract),
    ("format-fields", check_format_fields),
    ("claims", check_claims),
    ("merge-markers", check_merge_markers),
    ("shadowed-definitions", check_shadowed_definitions),
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
        scanned = sum(1 for rel in rels if _text_of(rel) is not None)
        print(f"\nGATE FAIL: {len(all_fails)} problem(s) across {scanned} of {len(rels)} tracked files.")
        return 1
    # What was SCANNED, not what is tracked. This said "{len(rels)} tracked files clean" while the
    # content checks read 108 of 138 and the merge-marker one 113, so the gate overstated its own reach
    # in the one line a reader takes away from it (Craig's agent, #249 class, on #239). Scanning by
    # content closed most of that gap; the line now names what is left, because a miss anybody can
    # enumerate is the point of the trade.
    skipped = sorted(rel for rel in rels if _text_of(rel) is None)
    print(f"\nGATE OK: {len(rels) - len(skipped)} of {len(rels)} tracked files clean across "
          f"{len(CHECKS)} checks"
          + (f"; {len(skipped)} not scanned as binary: {', '.join(skipped)}" if skipped else "")
          + ".")
    return 0


if __name__ == "__main__":
    sys.exit(main())
