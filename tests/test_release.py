"""The release check (#27): a tag is published only when it, the versions and the changelog agree."""
import sys
from pathlib import Path

import pytest

pytest.importorskip("tomllib")                      # Python 3.11 and newer; the release runs on 3.12
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packaging"))
import datetime  # noqa: E402

from check_release import check, main, release_notes  # noqa: E402

# The fixture dates its release 2026-10-01, and the check now asks a release to be dated the day its tag
# is cut, so every call that cuts one pins the clock to that day rather than drifting with the calendar.
FIXTURE_DAY = datetime.date(2026, 10, 1)


def _repo(tmp_path, version="0.1.0", code="0.1.0", heading="## [0.1.0] (2026-10-01)", cited=None,
          r_version=None):
    (tmp_path / "src" / "grownet").mkdir(parents=True)
    # the R companion's own version, which RELEASING.md calls the only signal an installed R copy is out
    # of date, so the check reads it too (#142 item 10)
    (tmp_path / "r").mkdir(parents=True)
    (tmp_path / "r" / "DESCRIPTION").write_text(f"Package: grownet\nVersion: {r_version or version}\n")
    (tmp_path / "pyproject.toml").write_text(f'[project]\nname = "grownet"\nversion = "{version}"\n')
    (tmp_path / "src" / "grownet" / "__init__.py").write_text(f'__version__ = "{code}"\n')
    # the citation names the version too: 0.1.0 shipped while CITATION.cff still said 0.0.2
    (tmp_path / "CITATION.cff").write_text(f'cff-version: 1.2.0\ntitle: grownet\n'
                                           f'version: {cited or version}\ndate-released: "2026-10-01"\n')
    (tmp_path / "CHANGELOG.md").write_text(f"# Changelog\n\n{heading}\n\n### Added\n- the first release\n\n"
                                           "## [0.0.2] (2026-09-01)\n\n- older\n")
    return tmp_path


def test_a_consistent_release_is_ready_and_its_notes_are_its_changelog_section(tmp_path):
    problems, notes = check("v0.1.0", _repo(tmp_path), today=FIXTURE_DAY)
    assert problems == [] and notes == "### Added\n- the first release"


@pytest.mark.parametrize("repo, tag, says", [
    ({}, "v0.2.0", "does not match"),
    ({"code": "0.0.2"}, "v0.1.0", "__version__ is 0.0.2"),
    ({"heading": "## [0.1.0] (unreleased)"}, "v0.1.0", "still marks 0.1.0 unreleased"),
    ({"heading": "## [0.0.9] (2026-10-01)"}, "v0.1.0", "no section for 0.1.0"),
    ({"cited": "0.0.2"}, "v0.1.0", "CITATION.cff says version 0.0.2"),
])
def test_an_inconsistent_release_is_refused(tmp_path, repo, tag, says):
    problems, _ = check(tag, _repo(tmp_path, **repo))
    assert any(says in p for p in problems)


def test_the_release_notes_start_with_how_to_get_past_the_windows_warning(tmp_path, monkeypatch):
    # Karoline (2026-09-29): until the project has the reputation SignPath asks for, "we should explain to
    # users how to click through the warning instead"; on her Windows, More info was a link and Run anyway
    # appeared only after it
    notes = release_notes("v0.1.0", "### Added\n- the first release")
    assert notes.startswith("**Windows:** download `grownet-v0.1.0-windows.zip`")
    assert "**More info** link" in notes and "only then does a **Run anyway** button appear" in notes
    assert notes.endswith("### Added\n- the first release")
    import check_release
    monkeypatch.setattr(check_release, "check",
                        lambda tag, **kw: check(tag, _repo(tmp_path), today=FIXTURE_DAY, **kw))
    out = tmp_path / "notes.md"
    assert main(["v0.1.0", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == notes + "\n"


def test_what_a_user_reads_describes_a_release_not_our_branches():
    """Karoline, 2026-10-04, on the R install line in the help: "Will this still be valid after the
    release? The help should refer to the stage the tool is in when released."

    So the texts that ship with the tool, the help page and both READMEs, give what a reader of a release
    runs. Installing from a branch or a clone is a development step, and lives in CONTRIBUTING.md and in
    the agent notes instead.
    """
    import re
    from pathlib import Path

    from grownet import gui
    from grownet import help as help_page

    root = Path(__file__).resolve().parents[1]
    shipped = {
        "the help page": help_page.render_help("tok", gui.DEFAULTS, gui.EXAMPLE),
        "README.md": root.joinpath("README.md").read_text(encoding="utf-8"),
        "r/README.md": root.joinpath("r", "README.md").read_text(encoding="utf-8"),
        # the page itself, which quotes the same lines (Karoline, 2026-10-04: "please check the GUI also
        # for the same problem")
        "the page": gui.render_form("tok"),
        "the page in gLV mode": gui.render_form("tok", settings=gui.glv_mode(dict(gui.DEFAULTS))),
        "the about page": gui.render_about("tok"),
        "the page without a token": gui.render_token_page(False, 8791),
    }
    # a branch of ours in an install line, or a promise about what happens "after it is merged"
    unreleased = re.compile(r"(?i)install_github\([^)]*\bref\s*=|until it is merged|once it is merged|"
                            r"on the branch|unreleased|not yet released|work in progress")
    for what, text in shipped.items():
        found = unreleased.search(text)
        assert not found, f"{what} describes work in progress, not a release: {found.group(0)!r}"

    # and no text names the branch this is being written on, when that is not main
    import subprocess
    branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True,
                            cwd=root).stdout.strip()
    if branch and branch != "main" and branch != "HEAD":
        for what, text in shipped.items():
            assert branch not in text, f"{what} names the branch {branch!r}, which no release will have"


def test_the_r_package_version_is_part_of_the_release_check(tmp_path):
    """#142 item 10: `check_release.py` did not read `r/DESCRIPTION`, which RELEASING.md calls the only
    signal an installed R copy is out of date, so a release could ship an R package that cannot tell a
    reader to update."""
    problems, _ = check("v0.1.0", _repo(tmp_path, r_version="0.0.9"))
    assert any("r/DESCRIPTION says Version 0.0.9" in p for p in problems), problems


def test_the_check_runs_with_no_tag_against_this_tree(tmp_path, capsys):
    """#142 item 15: the check appeared only in release.yml, on $GITHUB_REF_NAME, so the gate that
    catches a citation date drifting from the changelog fired for the first time when somebody pushed the
    tag. With no argument it checks the version this tree would release, which is what `make check` and
    CI now run on every build."""
    from check_release import current_version
    assert current_version() == __import__("grownet").__version__
    assert main([]) == 0
    assert "is ready" in capsys.readouterr().out


def test_a_tree_in_development_can_be_green_and_honest_at_once(tmp_path):
    """#155 item 8. With no tag the check asks about the version this tree would release, and a tree in
    development marks that version unreleased, which is the Keep a Changelog convention this file follows.
    Treating that as a problem left two green states: leave the version at the last released one, or mark
    the next release released before it is. The tree took the second and a test pinned it.

    So "still marks unreleased" is a problem only when a release is actually being cut.
    """
    repo = _repo(tmp_path, heading="## [0.1.0] (unreleased)")
    assert check("v0.1.0", repo, releasing=False)[0] == []
    problems, _ = check("v0.1.0", repo, releasing=True)
    assert any("still marks 0.1.0 unreleased" in p for p in problems)


def test_a_date_in_the_past_is_refused_on_the_day_a_tag_is_cut(tmp_path):
    """A past date passes every other check and can still be wrong, which is the state 0.3.0 sat in: on
    2026-10-08 CITATION.cff said 2026-10-07, the day it was prepared, and the changelog said "(unreleased)"
    and gave no date, so the two had nothing to disagree about and neither was in the future. Tagged a day
    later, that date would have shipped as the release date.

    So on the day a tag is cut the date has to be that day, with one day of slack for a tag pushed just
    after UTC midnight from a tree prepared the evening before. Hand computed against a fixed today.
    """
    import datetime

    today = datetime.date(2026, 10, 9)

    def repo_dated(name, when):
        root = _repo(tmp_path / name, heading=f"## [0.1.0] ({when})")
        (root / "CITATION.cff").write_text('cff-version: 1.2.0\ntitle: grownet\nversion: 0.1.0\n'
                                           f'date-released: "{when}"\n', encoding="utf-8")
        return root

    # the day itself, and the day before: both fine
    for when in ("2026-10-09", "2026-10-08"):
        assert not any("before today" in p
                       for p in check("v0.1.0", repo_dated(when, when), today=today)[0]), when
    # two days before: refused, with the remedy named
    problems, _ = check("v0.1.0", repo_dated("stale", "2026-10-07"), today=today)
    stale = [p for p in problems if "before today" in p]
    assert len(stale) == 2, problems                       # both files carry it, both are named
    assert all("2 days before today (2026-10-09)" in p for p in stale), stale
    assert any("set the date in CHANGELOG.md and CITATION.cff to today" in p for p in stale)
    # and it is a release-day rule only: preparing a tree with an older date is not a problem
    assert not any("before today" in p
                   for p in check("v0.1.0", repo_dated("prep", "2026-10-01"),
                                  releasing=False, today=today)[0])
    # the one-day slack is the constant, not a magic number in the message
    from check_release import STALE_DATE_DAYS
    assert STALE_DATE_DAYS == 1


def test_a_date_in_the_future_is_refused_however_it_is_written(tmp_path):
    """#155 item 8. The agreement check read only the parenthesized date, so `## [0.1.0] - 2099-01-01`
    was invisible to it: the heading and CITATION.cff could disagree in silence. And two files agreeing
    with each other is not either being right, so a date that has not happened yet is refused.
    """
    import datetime

    today = datetime.date(2026, 10, 7)
    # the dash form is read, so a disagreement in it is caught
    dashed = _repo(tmp_path / "a", heading="## [0.1.0] - 2026-10-02")
    problems, _ = check("v0.1.0", dashed, today=today)
    assert any("CHANGELOG.md says 2026-10-02" in p for p in problems), problems
    # a date in the future is refused even when both files carry it
    ahead = _repo(tmp_path / "b", heading="## [0.1.0] (2099-01-01)")
    (ahead / "CITATION.cff").write_text('cff-version: 1.2.0\ntitle: grownet\nversion: 0.1.0\n'
                                        'date-released: "2099-01-01"\n', encoding="utf-8")
    problems, _ = check("v0.1.0", ahead, today=today)
    assert sum("in the future" in p for p in problems) == 2, problems
    # and a release with no date at all is refused when one is being cut
    undated = _repo(tmp_path / "c", heading="## [0.1.0]")
    assert any("gives no date" in p for p in check("v0.1.0", undated, today=today)[0])
    assert not any("gives no date" in p for p in check("v0.1.0", undated, releasing=False, today=today)[0])


def test_this_tree_dates_its_release_no_earlier_than_its_newest_commit():
    """The dates said 2026-10-06 while every commit of the release was 2026-10-07, and because the two
    files agreed with each other the gate was silent (#155 item 8). This reads the tree, so it keeps
    them honest rather than only consistent.

    **It asks the question only while the tree is the release being prepared** (2026-10-10). Afterwards
    `__version__` still names the released version, its section is still dated, and every commit of the
    next cycle is newer than that date, so this failed on every pull request from the morning after
    0.3.0 shipped. The date of a release that has already happened is a fact about commits this tree no
    longer ends at, and re-checking it against a moving HEAD can only go wrong.

    The signal that the cycle has moved on is content under `## [Unreleased]`, which is what
    `RELEASING.md` says to start when work continues. The tag would say it exactly, but
    `actions/checkout` fetches no tags, so a tag-based check would pass locally and skip in CI, which is
    worse than this. The hole left is a commit made after a release that adds nothing to the changelog:
    it is rare, because every change here earns an entry, and it fails loudly rather than silently.
    """
    import datetime
    import re
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    changelog = root.joinpath("CHANGELOG.md").read_text(encoding="utf-8")
    version = re.search(r'^__version__ = "([^"]+)"', root.joinpath("src", "grownet", "__init__.py")
                        .read_text(encoding="utf-8"), re.M).group(1)
    section = re.search(rf"^## \[{re.escape(version)}\]([^\n]*)", changelog, re.M)
    assert section, f"CHANGELOG.md has no section for {version}"
    if "unreleased" in section.group(1).lower():
        # the documented process (RELEASING.md) dates the section in the release pull request, so a tree
        # in development carries no date and there is nothing to compare. Requiring one here would be the
        # same trap as #155 item 8: a check that cannot be green and honest at once, which is what made
        # this tree carry a date while it was unreleased in the first place.
        return
    heading = re.search(r"([0-9]{4}-[0-9]{2}-[0-9]{2})", section.group(1))
    assert heading, f"CHANGELOG.md gives {version} neither a date nor 'unreleased'"
    unreleased = re.search(r"^## \[Unreleased\]\s*\n(.*?)(?=^## \[)", changelog, re.M | re.S)
    if unreleased and unreleased.group(1).strip():
        return          # the next cycle has begun; this release's date is a fact about commits behind us
    dated = datetime.date.fromisoformat(heading.group(1))
    newest = subprocess.run(["git", "log", "-1", "--format=%cs"], capture_output=True, text=True,
                            cwd=root).stdout.strip()
    if newest:                      # a tarball has no git history, and then there is nothing to compare
        assert dated >= datetime.date.fromisoformat(newest), (
            f"the release is dated {dated} and its newest commit is {newest}")


def test_the_sdist_carries_every_doc_the_suite_reads(tmp_path):
    """A test that reads a shipped document makes that document a dependency of the suite, and the sdist
    job is the only one that notices when it is not carried: it unpacks the archive, where the repository
    layout is not there to fall back on. That went red once already, on the surface guard added for #202,
    and the prediction from the other side of the review was that it would go red once per new surface
    test, always after the test looked green locally (Craig's agent on #199, 2026-10-10).

    So this asserts the manifest covers them, which ends the sequence instead of paying for it one file at
    a time. It reads the paths out of the suite rather than listing them, so a new surface test is covered
    by this assertion the moment it is written.

    `README.md` is deliberately allowed without being named: setuptools ships the declared readme, which
    was measured in all five manifest shapes. That is a default rather than a promise, so it is recorded
    here instead of being relied on silently.
    """
    import re

    root = Path(__file__).resolve().parents[1]
    manifest = (root / "MANIFEST.in").read_text(encoding="utf-8")
    named = set()
    for line in manifest.splitlines():
        line = line.strip()
        if line.startswith("include "):
            named.update(line[len("include "):].split())
        elif line.startswith("recursive-include "):
            parts = line.split()
            named.update(f"{parts[1]}/**/{pat}" for pat in parts[2:])

    # TWO shapes, because the suite writes both and the first version of this saw only the first: a
    # whole relative path in one literal, and a COMPONENT JOIN, which is the dominant idiom here
    # (`root / "gui" / "index.html"`, `os.path.join(..., "docs", "legend.svg")`). Three files the suite
    # already reads were invisible, among them `schema/format_fields.json`, which `MANIFEST.in`'s own
    # comment names as the 2026-10-08 instance of this exact failure (found reviewing this change).
    whole = r'["\']((?:docs|examples|schema|gui|r)/[A-Za-z0-9_./-]+)["\']'
    joined_pattern = (r'["\'](docs|examples|schema|gui|r)["\']\s*[,/]\s*'
              r'(?:["\']([A-Za-z0-9_.-]+)["\']\s*[,/]\s*)?["\']([A-Za-z0-9_.-]+\.[A-Za-z0-9]+)["\']')
    wanted = set()
    for path in sorted((root / "tests").glob("*.py")):
        source = path.read_text(encoding="utf-8")
        wanted.update(re.findall(whole, source))
        for top, middle, leaf in re.findall(joined_pattern, source):
            wanted.add("/".join(x for x in (top, middle, leaf) if x))

    def covered(name: str) -> bool:
        if name in named or name == "README.md":
            return True
        import fnmatch
        folder, _, base = name.rpartition("/")
        for entry in named:
            if "/**/" in entry:
                top, pat = entry.split("/**/", 1)
                if (folder == top or folder.startswith(top + "/")) and fnmatch.fnmatch(base, pat):
                    return True
        return False

    missing = sorted(n for n in wanted if not covered(n))
    assert not missing, (
        "the suite reads these and MANIFEST.in does not carry them, so the sdist job will fail where "
        f"`make check` passes: {missing}")
    # and the assertion is reachable, which the first version of this could not show: the two it was
    # written for are in the set, and so are the three that a component join hid
    assert {"docs/METHOD_NOTES.md", "docs/LIMITATIONS.md"} <= wanted
    assert {"gui/index.html", "schema/format_fields.json", "docs/legend.svg"} <= wanted

    # a positive control for the extraction itself: both shapes are found, and a doc the manifest does
    # not carry is reported rather than passing. This is what the first version could not do, so a new
    # surface test written in the suite's own idiom went unnoticed.
    # A positive control for the extraction, written to a FILE rather than embedded here, because this
    # file is one of the files the extraction scans: embedded, the control's own paths were found in the
    # suite and the test failed on them, which is the guard working.
    def paths_in(source: str) -> set:
        out = set(re.findall(whole, source))
        for top, middle, leaf in re.findall(joined_pattern, source):
            out.add("/".join(x for x in (top, middle, leaf) if x))
        return out

    # the sample's paths are built from variables, so no path literal of the control appears in THIS
    # file: written out, the extraction found them here and the test failed on its own control
    # one per line: a TUPLE of string literals reads as a component join to the extraction, which is a
    # false positive mode worth knowing, and it caught this very line
    top = "docs"
    leaf_join = "SAMPLE.md"
    leaf_whole = "WHOLE.md"
    viewer = "index.html"
    probe = tmp_path / "test_probe.py"
    probe.write_text(
        "from pathlib import Path\nimport os\n\n\ndef test_x():\n"
        f'    a = (Path(".") / "{top}" / "{leaf_join}").read_text()\n'
        f'    b = open("{top}/{leaf_whole}").read()\n'
        f'    c = os.path.join("gui", "{viewer}")\n',
        encoding="utf-8")
    found = paths_in(probe.read_text(encoding="utf-8"))
    assert f"{top}/{leaf_join}" in found, "a component join is invisible to the extraction"
    assert f"{top}/{leaf_whole}" in found, "a whole path is invisible to the extraction"
    assert f"gui/{viewer}" in found, "an os.path.join is invisible to the extraction"
    assert not covered(f"{top}/{leaf_join}"), "the coverage test would pass a file the manifest lacks"
    assert covered(f"{top}/METHOD_" + "NOTES.md"), "the coverage test would fail a carried file"
