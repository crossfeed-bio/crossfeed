"""Saying on the page when a package will hold several matrices (#130, from #124 item 7).

Karoline, 2026-10-06: "OK for 4) then, with your recommendation of no default factor and a line in the
result section." No conversion between abundance units, since the measurement on #124 found that no arc
in mGrowthDB crosses them; what was missing is that the page said nothing before a reader downloaded.
"""
from grownet import matrix
from grownet.mgrowthdb import records_to_network


def _rate(name, unit):
    return {"name": name, "rate": 0.4, "unit": "1/h", "capacity": 1.0e9, "capacity_unit": unit,
            "capacity_n": 3, "method": "growth_rate:easylinear:5", "lag": 0.0, "lag_method": "baranyi"}


def _arc(source, target, unit):
    return {"source": source, "target": target, "source_name": source.upper(),
            "target_name": target.upper(), "effect": "facilitation", "strength": 1.0, "status": "present",
            "outcome": "quantified", "study_id": "S1", "metric": "growth_rate:easylinear:5",
            "evidence": "biculture", "partner_abundance": 2.0e8, "partner_abundance_unit": unit,
            "partner_abundance_n": 3, "metric_with": 0.8, "metric_without": 0.4}


def test_the_units_a_package_would_partition_by_are_the_ones_measured():
    net = records_to_network([_arc("b", "a", "Cells/mL"), _arc("d", "c", "CFUs/mL")])
    rates = {"a": _rate("A", "Cells/mL"), "b": _rate("B", "Cells/mL"),
             "c": _rate("C", "CFUs/mL"), "d": _rate("D", "CFUs/mL")}
    assert matrix.abundance_units(net, rates) == ["CFUs/mL", "Cells/mL"]
    one = records_to_network([_arc("b", "a", "Cells/mL")])
    assert matrix.abundance_units(one, {"a": _rate("A", "Cells/mL"), "b": _rate("B", "Cells/mL")}) == \
        ["Cells/mL"]
    assert matrix.abundance_units(one, {}) == ["Cells/mL"]      # from the arcs alone, with no rates yet


def test_the_result_section_says_how_many_matrices_the_package_will_hold():
    """The line Karoline asked for: before the download, not only in the package's own README."""
    from grownet.gui import render_result
    net = records_to_network([_arc("b", "a", "Cells/mL"), _arc("d", "c", "CFUs/mL")])
    rates = {"a": _rate("A", "Cells/mL"), "b": _rate("B", "Cells/mL"),
             "c": _rate("C", "CFUs/mL"), "d": _rate("D", "CFUs/mL")}
    result = {"network": net, "rates": rates, "entries": [], "resolved": [], "unresolved": [],
              "studies": ["S1"], "skipped": [], "errors": [], "hidden": {}, "absence": {"k": 1.0},
              "settings": {}, "reasons": {}, "suggestions": {}, "excluded": [], "genera": {},
              "taxon_ids": [], "partners_only": 0, "absent": None, "all": False}
    page = render_result("tok", result)
    assert "2 matrices" in page and "CFUs/mL" in page and "Cells/mL" in page
    assert "No effect between them" in page and "separate systems" in page

    # one unit, the usual case: nothing new on the page
    result["network"] = records_to_network([_arc("b", "a", "Cells/mL")])
    result["rates"] = {"a": _rate("A", "Cells/mL"), "b": _rate("B", "Cells/mL")}
    assert "matrices" not in render_result("tok", result)


def test_the_page_describes_the_package_it_now_writes():
    """Shipped text says what the release does: the package holds fitted coefficients per abundance unit,
    not a matrix with -1 on the diagonal (#119)."""
    from grownet.gui import render_result
    net = records_to_network([_arc("b", "a", "Cells/mL")])
    result = {"network": net, "rates": {"a": _rate("A", "Cells/mL"), "b": _rate("B", "Cells/mL")},
              "entries": [], "resolved": [], "unresolved": [], "studies": ["S1"], "skipped": [],
              "errors": [], "hidden": {}, "absence": {"k": 1.0}, "settings": {}, "reasons": {},
              "suggestions": {}, "excluded": [], "genera": {}, "taxon_ids": [], "partners_only": 0,
              "absent": None, "all": False}
    page = render_result("tok", result)
    assert "-1 on the diagonal" not in page
    assert "per-capita" in page or "coefficient" in page
