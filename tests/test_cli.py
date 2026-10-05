"""CLI behavior: an empty result is explained, not silent; validate reports problems."""
import json

from grownet.__main__ import main


def test_empty_network_is_explained(tmp_path, capsys):
    # a study that yields no records (here, an empty record set) must say so, not print a silent empty JSON
    fixture = tmp_path / "empty.json"
    fixture.write_text("[]", encoding="utf-8")
    rc = main(["derive", "SMGDB00000008", "--fixture", str(fixture)])
    out = capsys.readouterr()
    assert rc == 0
    assert json.loads(out.out)["edges"] == []          # still a valid, empty network on stdout
    assert "NO interactions were derived" in out.err
    assert "METHOD_NOTES" in out.err                    # points to the method choice


def test_validate_reports_problems(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({
        "schema": "grownet.interaction_network/v1", "nodes": [], "studies": [],
        "edges": [{"source": "a", "target": "b", "effect": "facilitation"}],  # no study_ids
    }), encoding="utf-8")
    rc = main(["validate", str(bad)])
    out = capsys.readouterr()
    assert rc == 1
    assert "study_ids" in out.err


def test_a_file_that_cannot_be_read_or_written_is_one_line_not_a_traceback(tmp_path, capsys, monkeypatch):
    # Karoline (2026-09-28), after a pip install from git: the README's fixture path, run outside a clone,
    # ended in a FileNotFoundError traceback
    monkeypatch.chdir(tmp_path)
    assert main(["derive", "SMGDB00000004", "--fixture", "tests/fixtures/example_interactions.json"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("grownet: tests/fixtures/example_interactions.json (relative to ")
    assert "No such file or directory" in err and "Traceback" not in err
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    assert main(["validate", str(bad)]) == 2
    assert "not valid JSON" in capsys.readouterr().err
    fixture = tmp_path / "empty.json"
    fixture.write_text("[]", encoding="utf-8")
    missing = str(tmp_path / "no_such_folder" / "out.json")
    assert main(["derive", "SMGDB00000008", "--fixture", str(fixture), "--out", missing]) == 2
    assert capsys.readouterr().err.startswith(f"grownet: {missing}: No such file or directory")
