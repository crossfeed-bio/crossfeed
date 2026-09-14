"""CLI behavior: an empty result is explained, not silent; validate reports problems."""
import json

from crossfeed.__main__ import main


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
        "schema": "crossfeed.interaction_network/v0", "nodes": [], "studies": [],
        "edges": [{"source": "a", "target": "b", "effect": "facilitation"}],  # no study_ids
    }), encoding="utf-8")
    rc = main(["validate", str(bad)])
    out = capsys.readouterr()
    assert rc == 1
    assert "study_ids" in out.err
