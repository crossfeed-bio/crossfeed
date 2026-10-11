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
    assert "at least 1" in why(["--min-studies", "0"])
    assert "every arc counts as 1" in why(["--min-studies", "2"])
    # the significance level, which the sibling --max-adjusted-p refuses above 1: an alpha of 5 switches
    # the no-growth rule off while `meta.no_growth` records it as the level the test ran at
    assert "at most 1" in why(["--no-growth-alpha", "5"])

    # EVERY flag in the negative-value loop, named from the function's own tuple rather than listed
    # here: the first version asserted three of the five, so dropping two from the loop left it green
    # and the page and the command line disagreed again about what is legal (found reviewing this
    # change)
    negatives = ["--spike-factor", "--capacity-max-fall", "--absence-threshold",
                 "--no-growth-alpha", "--no-growth-factor"]
    for flag in negatives:
        assert "cannot be negative" in why([flag, "-1"]), f"{flag} is not refused when negative"

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

    # EVERY entry, looped out of `_EMPTYING` itself rather than listed here. The first version asserted
    # three of the seven, so deleting the other four left it green and #220 returned for four real
    # controls; and the seventh entry, `min_replicates`, was DEAD, because the key is not in `DEFAULTS`
    # and the loop skipped it on every call, which no test could see (found reviewing this change).
    from grownet.gui import _EMPTYING

    # The membership is asserted EXPLICITLY, because looping over `_EMPTYING` cannot notice `_EMPTYING`
    # shrinking: deleting an entry just makes the loop check one thing fewer, which is what the first
    # version of this fix got wrong. The loop below then checks the behaviour of whatever is there.
    assert {key for key, _, _ in _EMPTYING} == {
        "min_studies", "spike_factor", "rate_window", "absence_threshold", "max_adjusted_p",
        "no_growth_factor"}, "a control was added to or removed from _EMPTYING without a decision"

    for key, label, _hint in _EMPTYING:
        assert key in DEFAULTS, f"{key} is not a page setting, so this entry can never fire"
        moved = 2 if isinstance(DEFAULTS[key], int) and not isinstance(DEFAULTS[key], bool) else 9.0
        if DEFAULTS[key] == moved:
            moved = moved + 1
        said = _settings_to_try({**DEFAULTS, key: moved})
        assert label in said, f"{label} is in _EMPTYING and _settings_to_try does not name it"

    said = _settings_to_try({**DEFAULTS, "min_studies": 2})
    assert "Arcs from at least N studies is 2" in said and "Merge arcs" in said

    said = _settings_to_try({**DEFAULTS, "spike_factor": 1.0})
    assert "Spike limit is 1.0" in said and "set it to 0" in said

    # two at once are both named, since either could be the cause
    said = _settings_to_try({**DEFAULTS, "min_studies": 2, "absence_threshold": 9.0})
    assert "Arcs from at least N studies" in said and "Absence threshold" in said


def test_an_incomplete_run_does_not_exit_zero_and_an_advisory_note_does_not_fail_one(monkeypatch):
    """`derive <a bad id> --live` exits 1 while the species and All paths collected the identical 404 into
    `errors` and exited 0, so a script could not tell a complete run from an incomplete one (#247).

    Keying the exit code on `errors` is safe only because that list is fetch failures and nothing else:
    the advisory messages (a setting that could not act, a check asked for and not run) travel in
    `notes`. Both halves are asserted, because keying on a list holding both would fail a COMPLETE run,
    which is how this nearly went onto the wrong branch.

    This drives `_derive_species` itself with a stubbed `run_query`, rather than restating the rule: the
    first version of this test recomputed the condition in a loop and would have passed against any
    implementation.
    """
    from grownet import __main__ as cli
    from grownet import gui
    from grownet.model import InteractionNetwork

    def answer(errors, notes):
        net = InteractionNetwork()
        return {"network": net, "skipped": [], "errors": list(errors), "notes": list(notes),
                "absence": {"absent": 0, "k": 1.0},
                "hidden": {"low_quality": 0, "absent": 0}, "studies": ["SMGDB00000001"],
                "unresolved": [], "suggestions": {}, "reasons": {}, "resolved": [], "settings": {},
                "entries": [], "taxon_ids": [], "rates": {}, "steady": None, "genera": {},
                "excluded": [], "all": False, "partners_only": 0}

    cases = [((), (), 0),
             ((), ("not used in Exclude these studies: SMGDB0000002",), 0),
             (("SMGDB0000002: mGrowthDB returned HTTP 404",), (), 1),
             (("SMGDB0000002: HTTP 404",), ("a note as well",), 1)]
    for errors, notes, wanted in cases:
        # bound now, not captured: ruff's B023 is right that a loop variable in a lambda is a trap
        monkeypatch.setattr(gui, "run_query",
                            lambda *a, _e=errors, _n=notes, **k: answer(_e, _n))
        monkeypatch.setattr(cli, "MGrowthDBClient", lambda *a, **k: object(), raising=False)
        args = cli.build_parser().parse_args(
            ["derive", "--live", "--species", "A", "--out", os.devnull])
        got = cli._derive_species(args)
        assert got == wanted, f"errors={errors} notes={notes} gave {got}, wanted {wanted}"
