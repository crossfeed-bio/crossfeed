"""CLI behavior: an empty result is explained, not silent; validate reports problems."""
import json
import os

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


def test_the_command_line_refuses_the_numbers_the_page_clamps():
    """The page coerces every numeric setting (`gui.parse_settings`) and the command line took them as
    typed, so the two disagreed about what is legal and a nonsense value travelled into `meta.settings`
    as the provenance of the run: `--rate-window -3` gave 0 edges and recorded -3, `--absence-threshold
    -1` gave 18 edges reported as "|log2 mean| < -1 * sd", `--no-growth-factor -2` gave 10 edges over 3
    nodes, each exiting 0 (#221 item 4).

    `--min-studies 2` is the other shape: a legal number that silently removes every arc, because without
    merging an arc carries no `studies` key and counts as 1 (#220).
    """
    from grownet.__main__ import _bad_settings, build_parser

    parser = build_parser()

    def why(extra):
        return _bad_settings(parser.parse_args(["derive", "S", "--live", *extra, "--out", os.devnull]))

    assert "at least 2 points" in why(["--rate-window", "-3"])
    assert "cannot be negative" in why(["--absence-threshold", "-1"])
    assert "cannot be negative" in why(["--no-growth-factor", "-2"])
    assert "cannot be negative" in why(["--spike-factor", "-1"])
    assert "at least 1" in why(["--min-studies", "0"])
    assert "every arc counts as 1" in why(["--min-studies", "2"])

    # the same value with merging on is legitimate and is not refused
    assert why(["--min-studies", "2", "--merge-arcs"]) == ""
    assert why(["--min-studies", "2", "--merge-genera"]) == ""
    # and nothing is refused at the defaults, or this would stop every run
    assert why([]) == ""
    assert why(["--rate-window", "5", "--absence-threshold", "1", "--spike-factor", "0"]) == ""


def test_a_setting_that_can_empty_the_network_is_named_when_it_does():
    """The page's notes blamed the species filter, then said "the species do not affect each other by that
    rule", then blamed mGrowthDB's replicate structure, while a control the reader had changed was
    discarding measured arcs and was never named (#220). This does not guess which setting did it; it says
    which ones could and what to try."""
    from grownet.gui import DEFAULTS, _settings_to_try

    assert _settings_to_try(dict(DEFAULTS)) == "", "nothing to say when every setting is a default"

    said = _settings_to_try({**DEFAULTS, "min_studies": 2})
    assert "Arcs from at least N studies is 2" in said and "Merge arcs" in said

    said = _settings_to_try({**DEFAULTS, "spike_factor": 1.0})
    assert "Spike limit is 1.0" in said and "set it to 0" in said

    # two at once are both named, since either could be the cause
    said = _settings_to_try({**DEFAULTS, "min_studies": 2, "absence_threshold": 9.0})
    assert "Arcs from at least N studies" in said and "Absence threshold" in said
