"""Choosing the integrated derivation on the page and on the command line (#127).

Karoline approved it "as an advanced option", so it is one setting, off by default, and the command line
has the same choice. The arithmetic is checked in tests/test_integrated.py; this file checks that the
choice reaches the derivation and that nothing changes when it is not made.
"""
import os

from test_gui import _query

from grownet.gui import DEFAULTS, glv_mode, parse_settings, render_form


def test_the_derivation_defaults_to_the_comparison_and_glv_mode_selects_the_integrated_form():
    """Karoline, 2026-10-10: "the default one, when we don't want to do simulations, should be the lenient
    one that allows for drop-out communities... I always thought that we were comparing derivers only for
    the gLV mode."

    She is right about the record: the table that chose the integrated form was measured with
    `--glv-mode`, which turns drop-out communities off on both sides, so it could not see that the
    integrated form derives no drop-out arc at all. On the corpus that is 145 arcs against 12, and 12
    censored bounds against none.

    Her decision of 2026-10-06 keeps its force where it was argued, which is the coefficient: "my
    decision would also be for the integrative form since it has support in publications and is not
    biased by construction." So gLV mode selects it, and nothing else does.
    """
    assert DEFAULTS["derivation"] == "replicate"
    assert glv_mode({})["derivation"] == "integrated"
    assert glv_mode(glv_mode({}), on=False)["derivation"] == "replicate"      # the button toggles back
    assert parse_settings({"derivation": ["integrated"]})["derivation"] == "integrated"
    assert parse_settings({"derivation": ["nonsense"]})["derivation"] == "replicate"


def test_the_setting_is_in_advanced_settings_with_both_choices():
    page = render_form("tok")
    settings = page[page.index("<details>"):]
    assert 'name="derivation"' in settings
    assert '<option value="replicate" selected>' in settings and 'value="integrated"' in settings
    assert "whole time course" in " ".join(settings.split())      # the muted text wraps in the source


def test_choosing_it_changes_the_arcs_and_says_which_derivation_made_them():
    """The fake study's curves are two points long, too short for a fit, so what this checks is that the
    choice reaches the derivation and that it reports rather than inventing: the network comes out empty
    and the reasons name the organisms."""
    result = _query(derivation="integrated")
    assert result["settings"]["derivation"] == "integrated"
    assert result["network"].meta["settings"]["derivation"] == "integrated"
    assert len(result["network"].edges) == 0
    assert result["skipped"]

    # and the default is untouched: the same search the usual way still gives the fake study's arc
    usual = _query()
    assert [(e.source, e.target) for e in usual["network"].edges]


def test_the_command_line_has_the_same_choice():
    from grownet.__main__ import build_parser
    derive = next(a for a in build_parser()._actions if a.dest == "cmd").choices["derive"]
    options = {o for action in derive._actions for o in action.option_strings}
    assert "--derivation" in options
    action = next(a for a in derive._actions if a.dest == "derivation")
    assert set(action.choices) == {"replicate", "integrated"}
    # The flag carries no default of its own: None means "not given", which is what lets gLV mode tell a
    # reader's explicit choice from one it filled in, and a run resolves None to the page's default. It
    # held "replicate" until 2026-10-10, when overriding an explicit flag was found to have broken the
    # decision register's own printed reproduction command.
    assert action.default is None


def test_the_choice_reaches_the_derivation_on_the_one_study_command(monkeypatch):
    """The test above checks the option exists; it ran no command, and the option did nothing on
    `grownet derive <STUDY>`, which reads a.derivation nowhere and ran the default derivation without
    saying so (found 2026-10-06). This runs that path and looks at the deriver it builds and at what the
    network records, which is what the requirement was about."""
    import grownet.__main__ as cli
    from grownet.integrated import IntegratedDeriver
    from grownet.mgrowthdb import MGrowthDBClient

    seen = {}

    def fake_derive(client, study_id, deriver=None, **kwargs):
        seen["deriver"] = deriver
        return [], []

    monkeypatch.setattr("grownet.derive.derive_interactions", fake_derive)
    monkeypatch.setattr("grownet.mgrowthdb.data_versions", lambda *a, **k: {})
    monkeypatch.setattr(MGrowthDBClient, "_get", lambda self, *a, **k: {})

    parser = cli.build_parser()
    for choice, expected in (("integrated", IntegratedDeriver), ("replicate", type(None))):
        args = parser.parse_args(["derive", "SMGDB00000001", "--live", "--derivation", choice,
                                  "--out", os.devnull])
        cli._derive(args)
        assert isinstance(seen["deriver"], expected), choice


def test_the_report_names_the_derivation_that_ran(monkeypatch):
    """The report must name the derivation that produced the file, since the two answer different
    questions and a reader cannot tell from the arcs which one they hold.

    This also asserted `"integrated" in render_help("tok")`, under the name "and the help". That had no
    force: `render_help` takes a token and a job and no settings (`gui.py:409`), so it cannot name the
    derivation a search ran, and both halves of that assertion are properties of the static settings
    table, true whatever any search does. The help page's own claim is checked where it belongs, in
    tests/test_help.py, and the real property here is that the report FOLLOWS the setting, which the old
    assertion never checked either way (found reviewing this test, 2026-10-10).
    """
    from grownet.report import report_text

    integrated = report_text(_query(derivation="integrated"))
    assert "derivation" in integrated.lower() and "integrated" in integrated

    # and it says the other one when the other one ran, which is what makes the line informative
    replicate = report_text(_query())
    assert "integrated" not in replicate
    assert "replicate" in replicate
