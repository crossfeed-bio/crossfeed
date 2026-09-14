"""crossfeed guardrails: a re-runnable gate (run in CI and before committing).

Self-contained (no dependency on any private path), so it runs the same for every
contributor and in CI. Checks:
  1. no secret-like strings (api keys, tokens, private keys) in tracked text files
  2. no raw or pulled experimental data committed: data/ stays out of git, and .csv
     files are only allowed under tests/fixtures/ (the data-governance guardrail)
Tests run separately (pytest), in CI.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SECRET = re.compile(
    r"(?i)(?:api[_-]?key|secret|token|password|authorization|bearer)\s*[:=]\s*"
    r"['\"][A-Za-z0-9/\+=_\-\.]{16,}['\"]"
    r"|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)
TEXT_EXT = (".py", ".md", ".toml", ".yml", ".yaml", ".json", ".cfg", ".ini", ".txt")


def tracked_files():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
        return [p for p in out.stdout.splitlines() if p.strip()]
    except Exception:
        return []


def check_secrets(rels):
    hits = []
    for rel in rels:
        if not rel.endswith(TEXT_EXT):
            continue
        try:
            text = open(os.path.join(ROOT, rel), encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        if SECRET.search(text):
            hits.append(f"[secrets] secret-like string in {rel}")
    return hits


def check_no_raw_data(rels):
    bad = []
    for rel in rels:
        r = rel.replace("\\", "/")
        if r.startswith("data/"):
            bad.append(f"[no-raw-data] raw data committed: {r} (data/ must stay out of git)")
        elif r.endswith(".csv") and not r.startswith("tests/fixtures/"):
            bad.append(f"[no-raw-data] csv committed outside tests/fixtures/: {r}")
    return bad


def main():
    rels = tracked_files()
    if not rels:
        print("gate: not a git tree yet (nothing tracked); skipping file checks.")
        return 0
    fails = check_secrets(rels) + check_no_raw_data(rels)
    if fails:
        print("GATE FAIL:")
        for f in fails:
            print("  X", f)
        return 1
    print(f"GATE OK: {len(rels)} tracked files; no secrets, no raw data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
