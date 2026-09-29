"""The release check (#27): a tag is published only when it, the versions and the changelog agree."""
import sys
from pathlib import Path

import pytest

pytest.importorskip("tomllib")                      # Python 3.11 and newer; the release runs on 3.12
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packaging"))
from check_release import check, main, release_notes  # noqa: E402


def _repo(tmp_path, version="0.1.0", code="0.1.0", heading="## [0.1.0] (2026-10-01)"):
    (tmp_path / "src" / "grownet").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(f'[project]\nname = "grownet"\nversion = "{version}"\n')
    (tmp_path / "src" / "grownet" / "__init__.py").write_text(f'__version__ = "{code}"\n')
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
