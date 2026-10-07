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

try:
    import tomllib
except ModuleNotFoundError:          # Python 3.10: the release itself runs on 3.12
    tomllib = None

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
        # 0.3.0 was prepared with 0.2.0's release date still in CITATION.cff, which nothing read: the
        # citation widget and every generated BibTeX entry take the date from there (found 2026-10-06).
        heading = re.search(r"\(([0-9]{4}-[0-9]{2}-[0-9]{2})\)", section.group(1))
        if dated and heading and dated.group(1) != heading.group(1):
            problems.append(f"CITATION.cff dates the release {dated.group(1)}, CHANGELOG.md says "
                            f"{heading.group(1)}")
    # The R companion is versioned separately and RELEASING.md calls r/DESCRIPTION the only signal an
    # installed R copy is out of date, so a release that forgets it ships a package that cannot tell a
    # reader to update (#142 item 10).
    description = (root / "r" / "DESCRIPTION").read_text(encoding="utf-8")
    r_version = re.search(r"^Version: *(.+)$", description, re.M)
    if not r_version:
        problems.append("r/DESCRIPTION has no Version")
    elif r_version.group(1).strip() != version:
        problems.append(f"r/DESCRIPTION says Version {r_version.group(1).strip()}, pyproject.toml says "
                        f"{version}")
    return problems, notes


def current_version(root: Path = ROOT) -> str:
    """The version this working tree would release, for a check that is not given a tag."""
    return tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


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
    # `make check` and CI run this with no tag on every build, and the oldest interpreter the project
    # supports has no tomllib. Skipping cleanly is what lets the check live in the ordinary build at all
    # (#142 item 15).
    if tomllib is None:
        print("release check: skipped, reading pyproject.toml needs Python 3.11 or newer")
        return 0
    # With no tag, check the version this tree would release. The check used to appear only in
    # release.yml, invoked on $GITHUB_REF_NAME, so the gate that catches a citation date drifting from
    # the changelog fired for the first time when somebody pushed the tag, which is the moment it is most
    # expensive to act on: the release is being cut and the fix means retagging (Craig's agent on #138,
    # #142 item 15). `make check` runs it with no argument on every build.
    if not argv or argv[0] in ("--current", ""):
        argv = [f"v{current_version()}", *argv[1:]]
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
