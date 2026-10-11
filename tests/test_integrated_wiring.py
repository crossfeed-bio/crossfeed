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
    # "<details" and not "<details>": the settings block renders `<details open>` when a setting is
    # not at its default, so that a reader is told (#250). This is a LOCATOR for the block, not the
    # requirement the test pins.
    settings = page[page.index("<details"):]
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


def test_a_derivation_without_a_no_growth_rule_says_so_rather_than_reporting_none():
    """`meta.no_growth` comes from the DERIVATION, not from the settings.

    It was built from the settings for every derivation, so the integrated form published
    `{"applied": true, "obligate": 0, "abolished": 0}`. A reader of the All artifact concluded that the
    rule had run over all 25 studies and found no organism in mGrowthDB that grows only with a partner;
    the comparison finds 15 on the same corpus the same day, measured 2026-10-11. Present and wrong is
    worse than missing, because a reader trusts it (#215 item 1).

    A censored arc CAN exist under that form, from the fit rather than from this rule (#201), so the
    reason says where one comes from instead of implying there are none.
    """
    from grownet.derive import Deriver, output_meta
    from grownet.integrated import IntegratedDeriver

    records = [{"source": "a", "target": "b", "source_name": "A", "target_name": "B",
                "effect": "inhibition", "strength": None, "weight": None, "status": "present",
                "outcome": "obligate", "study_id": "S1", "metric": "auc"}]

    def meta_for(deriver):
        _edges, meta = output_meta(list(records), deriver=deriver)
        return meta

    rule = meta_for(Deriver())["no_growth"]
    assert rule["applied"] is True
    assert rule["obligate"] == 1, rule        # the comparison counts what the rule produced

    none = meta_for(IntegratedDeriver())["no_growth"]
    assert none["applied"] is False
    # and NO count, because a 0 there reads as a measurement
    assert "obligate" not in none and "abolished" not in none, none
    assert "no no-growth rule" in none["why"]
    assert "bound_rule" in none["why"]        # where a censored arc under this form does come from


def test_a_setting_the_derivation_does_not_read_is_recorded_as_such():
    """The settings block printed every key with no derivation awareness, so under the integrated form a
    reader saw "Include drop-out communities: on" where it derives none, and changing `--metric` gave
    byte-identical networks while the recorded value changed (#215 item 3, the mechanism of #194).

    The list travels in `meta` so a reader of the FILE sees it, not only a reader of the report.
    """
    from grownet.derive import Deriver
    from grownet.integrated import IntegratedDeriver

    assert Deriver.ignores == ()
    ignored = set(IntegratedDeriver.ignores)
    # the ones measured as inert under that form
    assert {"metric", "rate_method", "rate_window", "include_dropout"} <= ignored, ignored
    assert {"no_growth_alpha", "no_growth_factor"} <= ignored, ignored
    # and not the ones it does read, or the mark would be a lie in the other direction
    for key in ("absence_threshold", "correction", "max_adjusted_p", "merge_arcs", "include_absent"):
        assert key not in ignored, key

    # the report marks them, and only them
    from grownet.help import SETTINGS
    assert all(k in SETTINGS for k in ignored), "a key nothing renders cannot be marked"
