"""Check a release tag before anything is published, and write its release notes (#27).

Usage: python packaging/check_release.py v0.1.0 notes.md

The tag must be v plus the version in pyproject.toml, the package's __version__ must be the same,
CITATION.cff must name that version, and CHANGELOG.md must hold a section for it that is no longer marked
unreleased. The notes file gets that section, for the GitHub release, after a paragraph on starting the
Windows program.

CITATION.cff is checked because 0.1.0 shipped while it still said 0.0.2: nothing read it, so nothing
caught it, and a citation that misstates the version is exactly the kind of thing a reader trusts.
"""
import re
import sys
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[1]


def check(tag: str, root: Path = ROOT) -> tuple:
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    init = (root / "src" / "grownet" / "__init__.py").read_text(encoding="utf-8")
    code_version = re.search(r'__version__ = "([^"]+)"', init).group(1)
    problems = []
    if tag != f"v{version}":
        problems.append(f"the tag {tag} does not match pyproject.toml's version {version} (expected v{version})")
    if code_version != version:
        problems.append(f"__version__ is {code_version}, pyproject.toml says {version}")
    citation = (root / "CITATION.cff").read_text(encoding="utf-8")
    cited = re.search(r"^version: *\"?([^\"\n]+)\"?$", citation, re.M)
    if not cited:
        problems.append("CITATION.cff has no version")
    elif cited.group(1).strip() != version:
        problems.append(f"CITATION.cff says version {cited.group(1).strip()}, pyproject.toml says {version}")
    dated = re.search(r"^date-released: *\"?([0-9]{4}-[0-9]{2}-[0-9]{2})\"?$", citation, re.M)
    if not dated:
        problems.append("CITATION.cff has no date-released")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    section = re.search(rf"^## \[{re.escape(version)}\](.*?)$(.*?)(?=^## \[|\Z)", changelog, re.M | re.S)
    if not section:
        problems.append(f"CHANGELOG.md has no section for {version}")
        notes = ""
    else:
        if "unreleased" in section.group(1).lower():
            problems.append(f"CHANGELOG.md still marks {version} unreleased")
        notes = section.group(2).strip()
    return problems, notes


# First on every release page, where Windows users download the program: it is unsigned until the project
# can show the reputation SignPath asks for, so the click-through is explained where the zip is (Karoline,
# 2026-09-29). "More info" is a small link; "Run anyway" appears only after it (her test on Windows).
WINDOWS = """**Windows:** download `grownet-{tag}-windows.zip` below, unzip it (right-click, Extract All) and \
double-click `grownet.exe` in the extracted folder. The first time, Windows shows "Windows protected your \
PC". Click the small **More info** link under the message; only then does a **Run anyway** button appear, \
and clicking it starts grownet. Windows says this about any program that few people have run yet, and \
grownet is new: it is built in public from this repository by its release workflow. With Smart App \
Control on (Windows 11) there may be no Run anyway; then install with `uv tool install grownet` or \
`pipx install grownet` instead (see the README).

**Everyone else:** `uv tool install grownet` or `pipx install grownet`, then `grownet gui`."""


def release_notes(tag: str, section: str) -> str:
    """The GitHub release's notes: how to start the program on Windows, then the changelog section."""
    return WINDOWS.format(tag=tag) + "\n\n" + section


def main(argv) -> int:
    tag, notes_file = argv[0], (argv[1] if len(argv) > 1 else None)
    problems, notes = check(tag)
    for p in problems:
        print(f"release check: {p}", file=sys.stderr)
    if problems:
        return 1
    if notes_file:
        Path(notes_file).write_text(release_notes(tag, notes) + "\n", encoding="utf-8")
    print(f"release check: {tag} is ready")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
