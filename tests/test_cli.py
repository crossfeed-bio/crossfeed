"""CLI behavior: an empty result is explained, not silent; validate reports problems."""
import json
import os

import pytest

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
    typed, so the two disagreed about what is legal and a nonsense value reached `meta.settings`
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

    # EVERY flag in the negative-value loop, listed here rather than read from the function's own
    # tuple, which is the point: the first version asserted three of the five, so dropping two from the
    # loop left it green and the page and the command line disagreed again about what is legal (found
    # reviewing this change). A loop over the function's tuple would shrink with it and notice nothing.
    negatives = ["--spike-factor", "--capacity-max-fall", "--absence-threshold",
                 "--no-growth-alpha", "--no-growth-factor"]
    for flag in negatives:
        assert "cannot be negative" in why([flag, "-1"]), f"{flag} is not refused when negative"

    # the same five again, non-finite. `nan < 0` and `inf < 0` are both False, so the bound above does
    # not catch either, and `float()` accepts all three of these spellings. Unrefused, the value reaches
    # `meta.settings` and `json.dumps` writes `NaN` or `Infinity`, which RFC 8259 section 6 forbids: R
    # refuses the whole network while grownet's own `validate` accepts it (#258)
    for flag in negatives:
        for text in ("nan", "inf", "1e999"):
            assert "must be a finite number" in why([flag, text]), f"{flag} {text} is not refused"
    # --max-adjusted-p needs no entry above: its own argparse type refuses anything outside
    # `0 < value <= 1`, and `nan` and `inf` both fail that, so the parser stops before _bad_settings runs
    for text in ("nan", "inf"):
        with pytest.raises(SystemExit):
            why(["--max-adjusted-p", text])

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
    # version of this fix got wrong. The loop below then checks the behavior of whatever is there.
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


def _parsed(extra_args):
    """A complete argument namespace, from the real parser, so every attribute `_emit` reads exists."""
    from grownet.__main__ import build_parser
    return build_parser().parse_args(["derive", "S", "--fixture", os.devnull, *extra_args])


def _one_arc_network():
    from grownet.mgrowthdb import records_to_network
    return records_to_network(
        [{"source": "A organism", "target": "B organism", "effect": "facilitation", "study_id": "S1",
          "log2_mean": 1.0, "strength": 1.0, "q_value": 0.01, "significance": 2.0}],
        meta={"tool_version": "9.9.9", "source_db": "mGrowthDB (fixture)"})


def test_asking_for_a_rates_file_that_could_not_be_written_does_not_exit_zero(tmp_path, capsys):
    """`--rates`, `--glv` and `--to-r` with no computable rate print the cause and exit 1.

    The exit code is carried to the END of `_emit`, after the skipped pairs, the absence note and the
    "NO interactions were derived" explanation, because the diagnosis is what the person needs: the
    earlier `return 1` printed 7 lines of stderr where asking for less printed 74 (#221 item 3). Carrying
    it that far is the part that can be lost without anything noticing, and nothing tested it: replacing
    the final `return 1 if no_rates else 0` with `return 0` left all 718 tests green (found reviewing
    round 10).
    """
    from grownet.__main__ import _emit

    a = _parsed(["--rates", str(tmp_path / "r.csv"), "--out", os.devnull])
    result = {"rates": {}, "skipped": [], "errors": [], "settings": {}}
    code = _emit(a, _one_arc_network(), [], None, "S", result)
    assert code == 1, "asking for a file the run could not write exited 0"
    err = capsys.readouterr().err
    assert "--rates" in err and "wrote nothing" in err
    # and the flag that was NOT asked for is not blamed
    assert "--glv" not in err and "--to-r" not in err
    # with a rate to write, the same call exits 0
    rates = {nid: {"name": nid, "rate": 0.5, "unit": "1/h", "n": 3, "studies": ["S1"],
                   "method": "easylinear", "lag": None, "lag_method": "", "per_study": {"S1": 0.5}}
             for nid in _one_arc_network().nodes}
    assert _emit(_parsed(["--rates", str(tmp_path / "r2.csv"), "--out", os.devnull]),
                 _one_arc_network(), [], None, "S", {"rates": rates, "skipped": [], "errors": [],
                                                     "settings": {}}) == 0


def test_the_skipped_count_counts_pairs_and_names_the_notes_separately(capsys):
    """The heading counts pairs and notes apart, because counting them together answered a question
    nobody asked.

    On the live corpus 97 of 186 entries were average-replicate notes keyed by experiment and 31 named
    conditions that DID produce reported arcs, so the report called a condition a pair that gave no edge
    254 lines after reporting an interaction derived from it (#232). `tests/test_derive.py` tests
    `about_a_pair` as a predicate and nothing asserted that any OUTPUT used it: reverting this heading to
    one count over everything left the suite green.
    """
    from grownet.__main__ import _emit
    from grownet.adapter import AVERAGE

    skipped = [("A organism with B organism [EXP_1]", "no monoculture replicates"),
               ("C organism with D organism [EXP_2]", "one side did not grow"),
               ("EXP_3: rep1", AVERAGE)]
    code = _emit(_parsed(["--out", os.devnull]), _one_arc_network(), skipped, None, "S",
                 {"rates": {}, "skipped": skipped, "errors": [], "settings": {}})
    err = capsys.readouterr().err
    assert code == 0
    assert "skipped 2 pair(s)" in err, err          # the two that are pairs, not all three
    assert "1 note(s) on the data read" in err      # and the average row named as what it is


def test_a_single_study_run_refuses_a_flag_that_narrows_several(tmp_path, capsys):
    """`--exclude-studies` and `--all-partners` narrow a search over several studies, so a run of one
    study refuses them rather than recording them as applied.

    #242 made the record truthful, which left the contradiction: the report would say the study was
    excluded while every arc comes from it. Nothing tested the refusal, so replacing the comprehension
    with an empty list left the suite green and `derive <STUDY> --exclude-studies <that study>` derived
    the study again (found reviewing round 10).
    """
    from grownet.__main__ import main

    fixture = tmp_path / "records.json"
    fixture.write_text("[]", encoding="utf-8")
    for flag, value in (("--exclude-studies", "SMGDB00000004"), ("--all-partners", None)):
        args = ["derive", "SMGDB00000004", "--fixture", str(fixture), "--out", os.devnull, flag]
        if value is not None:
            args.append(value)
        assert main(args) == 2, f"{flag} was not refused on a single-study run"
        err = capsys.readouterr().err
        assert flag in err and "would be recorded and not applied" in err


def test_the_fixture_route_refuses_a_setting_it_cannot_apply(tmp_path, capsys):
    """`--fixture` holds records someone already derived, and NO setting changes its arcs.

    Measured rather than reasoned, with a fixture built so each setting had something to act on (the same
    pair from two studies for merging, a q-value of 0.40 for the filter, a tiny effect with a spread for
    the threshold, a single_replicate arc for the quality filter): every one of fourteen left the arcs
    byte-identical. The mechanism is that `output_meta` runs only on the live path, so this route has no
    output stage at all. Ten or more settings were accepted and discarded in silence (#222 item 1).

    Refusing is the half of "refuse or announce" a command can do, which is what #221 settled for every
    other setting, and `--deriver` already does it here in almost these words.
    """
    import json as _json

    from grownet.__main__ import main

    fixture = tmp_path / "records.json"
    fixture.write_text(_json.dumps([
        {"source": "a", "target": "b", "source_name": "A", "target_name": "B", "effect": "facilitation",
         "strength": 1.0, "q_value": 0.01, "significance": 2.0, "study_id": "S1"}]), encoding="utf-8")
    base = ["derive", "SMGDB00000004", "--fixture", str(fixture), "--out", os.devnull]

    # a plain fixture run is untouched
    assert main(base) == 0
    capsys.readouterr()

    for flag, value in (("--absence-threshold", "9"), ("--metric", "max"), ("--merge-arcs", None),
                        ("--max-adjusted-p", "0.01"), ("--correction", "by"),
                        ("--include-absent", None), ("--rate-window", "9")):
        args = base + [flag] + ([value] if value else [])
        assert main(args) == 2, f"{flag} was accepted on the fixture route"
        err = capsys.readouterr().err
        assert flag in err, err
        assert "already derived" in err


def test_a_route_that_applied_no_threshold_does_not_print_an_empty_one(tmp_path):
    """The report printed `(k = )` and an empty `settings:` heading on the fixture route, because it has
    no output stage: a count of arcs below a threshold that was never applied, and a heading that said
    the run had no settings rather than that it records none (#222 item 1)."""
    from grownet.mgrowthdb import records_to_network
    from grownet.report import report_text

    net = records_to_network([
        {"source": "a", "target": "b", "source_name": "A", "target_name": "B", "effect": "facilitation",
         "strength": 1.0, "q_value": 0.01, "significance": 2.0, "study_id": "S1"}])
    text = report_text({"network": net, "entries": [], "settings": {}, "resolved": [], "studies": [],
                        "skipped": [], "errors": [], "unresolved": [], "taxon_ids": {},
                        "suggestions": {}, "reasons": {}, "hidden": {}, "absence": {}})
    assert "(k = )" not in text, "a threshold that was never applied is printed as an empty number"
    assert "No absence threshold was applied" in text
    assert "settings: none recorded" in text
    assert "already derived" in text
