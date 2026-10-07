"""The release check (#27): a tag is published only when it, the versions and the changelog agree."""
import sys
from pathlib import Path

import pytest

pytest.importorskip("tomllib")                      # Python 3.11 and newer; the release runs on 3.12
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packaging"))
from check_release import check, main, release_notes  # noqa: E402


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
    problems, notes = check("v0.1.0", _repo(tmp_path))
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
    monkeypatch.setattr(check_release, "check", lambda tag: check(tag, _repo(tmp_path)))
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
