"""The gate's merge-marker check: a conflict left by a merge once reached the changelog unseen."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "checks"))
import gate  # noqa: E402


def test_conflict_markers_are_found_and_a_heading_underline_is_not(monkeypatch):
    files = {"CHANGELOG.md": "# Changes\n<<<<<<< HEAD\n- ours\n=======\n- theirs\n>>>>>>> origin/branch\n",
             "README.txt": "grownet\n=======\n\nStart it\n--------\n"}
    monkeypatch.setattr(gate, "_read", files.get)
    assert gate.check_merge_markers(list(files)) == [
        "conflict marker left from a merge in CHANGELOG.md, line 2",
        "conflict marker left from a merge in CHANGELOG.md, line 6"]
