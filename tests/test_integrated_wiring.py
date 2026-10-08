"""Choosing the integrated derivation on the page and on the command line (#127).

Karoline approved it "as an advanced option", so it is one setting, off by default, and the command line
has the same choice. The arithmetic is checked in tests/test_integrated.py; this file checks that the
choice reaches the derivation and that nothing changes when it is not made.
"""
import os

from test_gui import _query

from grownet.gui import DEFAULTS, parse_settings, render_form


def test_the_derivation_defaults_to_the_integrated_form():
    """Karoline, 2026-10-06, choosing it as the default: "my decision would also be for the integrative
    form since it has support in publications and is not biased by construction. That weights heavier
    than low coverage on data currently in mGrowthDB. By default, grownet should do what is 'correct'
    i.e. more defensible mathematically." The specified comparison stays as the alternative and keeps
    everything it had."""
    assert DEFAULTS["derivation"] == "integrated"
    assert parse_settings({"derivation": ["replicate"]})["derivation"] == "replicate"
    assert parse_settings({"derivation": ["nonsense"]})["derivation"] == "integrated"


def test_the_setting_is_in_advanced_settings_with_both_choices():
    page = render_form("tok")
    settings = page[page.index("<details>"):]
    assert 'name="derivation"' in settings
    assert '<option value="integrated" selected>' in settings and 'value="replicate"' in settings
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
    assert action.default == "integrated" and set(action.choices) == {"replicate", "integrated"}


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


def test_the_report_and_the_help_name_the_derivation(monkeypatch):
    from grownet.gui import render_help
    from grownet.report import report_text
    result = _query(derivation="integrated")
    text = report_text(result)
    assert "Derivation" in text or "derivation" in text
    assert "integrated" in text
    help_page = render_help("tok")
    assert "integrated" in help_page and "time course" in help_page
