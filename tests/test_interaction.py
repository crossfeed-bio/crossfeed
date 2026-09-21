"""Tests for the interaction strength helper (synthetic replicate curves, hand-computed values)."""
import math

import pytest

from crossfeed.growth import GrowthCurve, Replicate
from crossfeed.interaction import dropout_interaction_strengths, interaction_strength

A = "Faecalibacterium prausnitzii"
B = "Blautia hydrogenotrophica"


def _curve(species, values, times=(0, 10)):
    return GrowthCurve(species, times, values, "h", "16S copies/mL")


def _example():
    # Two-point curves over 10 h, so the area under the curve is 5 * (v0 + v1).
    mono_a = [Replicate([_curve(A, (1, 1))], "a1"),              # auc 10, max 1
              Replicate([_curve(A, (1, 3))], "a2")]              # auc 20, max 3
    mono_b = [Replicate([_curve(B, (1, 1))], "b1"),              # auc 10, max 1
              Replicate([_curve(B, (3, 5))], "b2")]              # auc 40, max 5
    co = [Replicate([_curve(A, (1, 3)), _curve(B, (1, 1))], "c1"),      # A auc 20; B auc 10
          Replicate([_curve(A, (3, 5)), _curve(B, (1, 0))], "c2")]      # A auc 40; B auc 5
    return mono_a, mono_b, co


def test_auc_default_matches_hand_computed_values():
    r = interaction_strength(*_example(), A, B)
    assert r["method"] == "auc" and r["log"] == "log2" and r["window"] == (0.0, 10.0)
    # A: log2 co = log2 20, log2 40 (mean log2 20 + 0.5, sd sqrt(0.5));
    #    log2 mono = log2 10, log2 20 (mean log2 10 + 0.5, sd sqrt(0.5))
    #    strength = 1, sd = sqrt(0.5 + 0.5) = 1, se = sqrt(0.5 / 2 + 0.5 / 2) = sqrt(0.5)
    a = r["species_a"]
    assert a["species"] == A and a["outcome"] == "quantified"
    assert a["mean"] == pytest.approx(1.0)
    assert a["sd"] == pytest.approx(1.0)
    assert a["se"] == pytest.approx(math.sqrt(0.5))
    assert (a["n_co"], a["n_mono"]) == (2, 2)
    assert a["co_log2"] == pytest.approx([math.log2(20), math.log2(40)])
    assert a["mono_log2"] == pytest.approx([math.log2(10), math.log2(20)])
    # B: log2 co = log2 10, log2 5 (mean log2 10 - 0.5, sd sqrt(0.5));
    #    log2 mono = log2 10, log2 40 (mean log2 10 + 1, sd sqrt(2))
    #    strength = -1.5, sd = sqrt(0.5 + 2) = sqrt(2.5), se = sqrt(0.5 / 2 + 2 / 2) = sqrt(1.25)
    b = r["species_b"]
    assert b["mean"] == pytest.approx(-1.5)
    assert b["sd"] == pytest.approx(math.sqrt(2.5))
    assert b["se"] == pytest.approx(math.sqrt(1.25))
    assert r["skipped"] == []


def test_max_method():
    r = interaction_strength(*_example(), A, B, method="max")
    # A: co maxima 3 and 5, mono maxima 1 and 3 -> (log2 3 + log2 5) / 2 - (0 + log2 3) / 2 = log2(5) / 2
    assert r["species_a"]["mean"] == pytest.approx(math.log2(5) / 2)
    # B: co maxima 1 and 1, mono maxima 1 and 5 -> 0 - log2(5) / 2
    assert r["species_b"]["mean"] == pytest.approx(-math.log2(5) / 2)


def test_single_replicate_per_set_has_no_sd_or_se():
    mono_a, mono_b, co = _example()
    r = interaction_strength(mono_a[:1], mono_b[:1], co[:1], A, B)
    # A: log2(20) - log2(10) = 1
    assert r["species_a"]["mean"] == pytest.approx(1.0)
    assert r["species_a"]["sd"] is None and r["species_a"]["se"] is None


def test_one_replicate_in_a_set_still_gives_no_sd():
    mono_a, mono_b, co = _example()
    r = interaction_strength(mono_a, mono_b, co[:1], A, B)
    # A: log2(20) - mean(log2 10, log2 20) = 0.5; the co-culture set has no spread to estimate
    assert r["species_a"]["mean"] == pytest.approx(0.5)
    assert r["species_a"]["sd"] is None


def test_non_positive_replicate_is_skipped():
    mono_a, mono_b, co = _example()
    co = co + [Replicate([_curve(A, (1, 1)), _curve(B, (0, 0))], "c3")]
    r = interaction_strength(mono_a, mono_b, co, A, B)
    # B's c3 area is 0: dropped from B's co-culture set only; A keeps all three co-culture replicates
    assert r["species_b"]["n_co"] == 2
    assert r["species_b"]["mean"] == pytest.approx(-1.5)
    assert r["species_a"]["n_co"] == 3
    assert r["skipped"] == [(f"{B}: co-culture replicate c3", "non-positive auc (0)")]


def test_growth_only_with_partner_is_obligate_not_an_error():
    mono_a, _, co = _example()
    mono_b = [Replicate([_curve(B, (0, 0))], "b0")]      # B does not grow alone, but grows in co-culture
    r = interaction_strength(mono_a, mono_b, co, A, B)
    b = r["species_b"]
    assert b["outcome"] == "obligate"
    assert (b["mean"], b["sd"], b["se"]) == (None, None, None)
    assert (b["n_co"], b["n_mono"]) == (2, 0)
    assert r["species_a"]["outcome"] == "quantified" and r["species_a"]["mean"] == pytest.approx(1.0)
    assert r["skipped"] == [(f"{B}: monoculture replicate b0", "non-positive auc (0)")]


def test_growth_only_alone_is_abolished_and_neither_is_no_growth():
    mono_a, mono_b, _ = _example()
    co = [Replicate([_curve(A, (1, 3)), _curve(B, (0, 0))], "c1")]    # B grows alone, not with A
    assert interaction_strength(mono_a, mono_b, co, A, B)["species_b"]["outcome"] == "abolished"
    none = [Replicate([_curve(B, (0, 0))], "b0")]
    b = interaction_strength(mono_a, none, co, A, B)["species_b"]
    assert b["outcome"] == "no_growth" and b["mean"] is None


def test_curves_are_cut_to_the_shared_window():
    mono_a, mono_b, co = _example()
    # a longer co-culture curve for A: over 0 to 10 h it is identical to c1's (1, 3)
    co[0] = Replicate([_curve(A, (1, 3, 9), times=(0, 10, 20)), _curve(B, (1, 1))], "c1")
    r = interaction_strength(mono_a, mono_b, co, A, B)
    assert r["window"] == (0.0, 10.0)
    assert r["species_a"]["mean"] == pytest.approx(1.0)


def test_errors_for_method_start_time_and_units():
    mono_a, mono_b, co = _example()
    with pytest.raises(ValueError, match="unknown method 'rate'"):
        interaction_strength(mono_a, mono_b, co, A, B, method="rate")
    late = [Replicate([_curve(B, (1, 1), times=(2, 10))], "b1")]
    with pytest.raises(ValueError, match="start at different time points"):
        interaction_strength(mono_a, late, co, A, B)
    days = [Replicate([GrowthCurve(B, (0, 10), (1, 1), "d", "16S copies/mL")], "b1")]
    with pytest.raises(ValueError, match="mixed time units"):
        interaction_strength(mono_a, days, co, A, B)


# ---- drop-out communities (#10) ----------------------------------------------------------------------

C = "Bacteroides thetaiotaomicron"


def _community(name, areas):
    """A replicate with one two-point curve per species; `areas` maps species to (v0, v1) over 10 h."""
    return Replicate([_curve(sp, v) for sp, v in areas.items()], name)


def _dropout_example():
    # Areas are 5 * (v0 + v1).
    full = [_community("f1", {A: (1, 3), B: (1, 1), C: (1, 1)}),      # A 20, B 10, C 10
            _community("f2", {A: (3, 5), B: (1, 1), C: (1, 3)})]      # A 40, B 10, C 20
    without_c = [_community("xc1", {A: (1, 1), B: (1, 1)}),           # A 10, B 10
                 _community("xc2", {A: (1, 3), B: (1, 1)})]           # A 20, B 10
    without_b = [_community("xb1", {A: (1, 3), C: (3, 5)}),           # A 20, C 40
                 _community("xb2", {A: (3, 5), C: (7, 9)})]           # A 40, C 80
    return full, {C: without_c, B: without_b}


def _arc(result, source, target):
    return next(a for a in result["arcs"] if a["source"] == source and a["target"] == target)


def test_dropout_arcs_match_hand_computed_values():
    full, dropouts = _dropout_example()
    r = dropout_interaction_strengths(full, dropouts)
    assert r["method"] == "auc" and r["log"] == "log2" and r["window"] == (0.0, 10.0)
    assert len(r["arcs"]) == 4 and r["skipped"] == []
    # C -> A: full A log2 20, log2 40; without C log2 10, log2 20 -> mean 1, sd sqrt(0.5 + 0.5), se sqrt(0.5)
    ca = _arc(r, C, A)
    assert ca["mean"] == pytest.approx(1.0)
    assert ca["sd"] == pytest.approx(1.0)
    assert ca["se"] == pytest.approx(math.sqrt(0.5))
    assert (ca["n_with"], ca["n_without"]) == (2, 2)
    assert ca["with_log2"] == pytest.approx([math.log2(20), math.log2(40)])
    assert ca["without_log2"] == pytest.approx([math.log2(10), math.log2(20)])
    # C -> B: 10, 10 in both -> mean 0, sd 0
    cb = _arc(r, C, B)
    assert cb["mean"] == pytest.approx(0.0) and cb["sd"] == pytest.approx(0.0)
    # B -> A: A is 20, 40 with and without B -> mean 0, sd 1
    ba = _arc(r, B, A)
    assert ba["mean"] == pytest.approx(0.0) and ba["sd"] == pytest.approx(1.0)
    # B -> C: full C log2 10, log2 20; without B log2 40, log2 80 -> mean -2
    assert _arc(r, B, C)["mean"] == pytest.approx(-2.0)
    for arc in r["arcs"]:
        assert arc["evidence"] == "dropout"
        assert arc["community"] == sorted([A, B, C])


def test_two_member_community_equals_mono_versus_biculture():
    mono_a, mono_b, co = _example()
    pair = interaction_strength(mono_a, mono_b, co, A, B)
    r = dropout_interaction_strengths(co, {B: mono_a, A: mono_b})
    ba, ab = _arc(r, B, A), _arc(r, A, B)
    for arc, side in ((ba, pair["species_a"]), (ab, pair["species_b"])):
        assert arc["evidence"] == "biculture"
        assert arc["mean"] == pytest.approx(side["mean"])
        assert arc["sd"] == pytest.approx(side["sd"])
        assert arc["se"] == pytest.approx(side["se"])


def test_dropout_set_errors():
    full, dropouts = _dropout_example()
    still_has_c = {C: [_community("x", {A: (1, 1), B: (1, 1), C: (1, 1)})]}
    with pytest.raises(ValueError, match=r"community without .* holds species"):
        dropout_interaction_strengths(full, still_has_c)
    lacks_b = {C: [_community("x", {A: (1, 1)})]}
    with pytest.raises(ValueError, match=r"community without .* holds species"):
        dropout_interaction_strengths(full, lacks_b)
    outsider = {"Escherichia coli": [_community("x", {A: (1, 1), B: (1, 1), C: (1, 1)})]}
    with pytest.raises(ValueError, match="not a member of the full community"):
        dropout_interaction_strengths(full, outsider)
    uneven = full + [_community("f3", {A: (1, 1), B: (1, 1)})]
    with pytest.raises(ValueError, match="full community replicate f3 holds species"):
        dropout_interaction_strengths(uneven, dropouts)
    with pytest.raises(ValueError, match="no drop-out sets"):
        dropout_interaction_strengths(full, {})
    with pytest.raises(ValueError, match="unknown method"):
        dropout_interaction_strengths(full, dropouts, method="rate")


def test_dropout_zero_growth_gives_obligate_and_abolished_arcs():
    full, dropouts = _dropout_example()
    # C does not grow without B: B is required for C's growth (obligate), and the arc is kept
    dropouts[B] = [_community("xb1", {A: (1, 3), C: (0, 0)}), _community("xb2", {A: (3, 5), C: (0, 0)})]
    r = dropout_interaction_strengths(full, dropouts)
    bc = _arc(r, B, C)
    assert bc["outcome"] == "obligate" and bc["mean"] is None
    assert (bc["n_with"], bc["n_without"]) == (2, 0)
    assert _arc(r, C, A)["outcome"] == "quantified"
    assert len(r["arcs"]) == 4
    # C grows only without B: B abolishes C's growth
    full, dropouts = _dropout_example()
    full = [_community("f1", {A: (1, 3), B: (1, 1), C: (0, 0)}), _community("f2", {A: (3, 5), B: (1, 1), C: (0, 0)})]
    r = dropout_interaction_strengths(full, {B: dropouts[B]})
    assert _arc(r, B, C)["outcome"] == "abolished"


def test_dropout_arc_without_growth_in_either_set_is_skipped():
    full, dropouts = _dropout_example()
    full = [_community("f1", {A: (1, 3), B: (1, 1), C: (0, 0)}), _community("f2", {A: (3, 5), B: (1, 1), C: (0, 0)})]
    dropouts[B] = [_community("xb1", {A: (1, 3), C: (0, 0)}), _community("xb2", {A: (3, 5), C: (0, 0)})]
    r = dropout_interaction_strengths(full, dropouts)
    assert {(a["source"], a["target"]) for a in r["arcs"]} == {(C, A), (C, B), (B, A)}
    reason = dict(r["skipped"])[f"arc {B} -> {C}"]
    assert reason == f"no growth (auc) in the full community or the community without {B}"


def test_dropout_full_community_skip_is_reported_once():
    full, dropouts = _dropout_example()
    # B does not grow in full community replicate f2: its arcs from C use f1 only, reported once
    full[1] = _community("f2", {A: (3, 5), B: (0, 0), C: (1, 3)})
    r = dropout_interaction_strengths(full, dropouts)
    assert r["skipped"] == [(f"{B}: full community replicate f2", "non-positive auc (0)")]
    cb = _arc(r, C, B)
    assert (cb["n_with"], cb["mean"], cb["sd"]) == (1, 0.0, None)


# ---- implausible spikes (#39) --------------------------------------------------------------------

def _spiked(species, base):
    """A two-point-like curve with one absurd point in the middle; its area is dominated by the spike."""
    return GrowthCurve(species, (0, 5, 10), (base, base * 1e5, base), "h", "16S copies/mL")


def test_a_spiked_monoculture_replicate_is_left_out_and_reported():
    mono_a, mono_b, co = _example()
    mono_b = mono_b + [Replicate([_spiked(B, 1.0)], "b_spike")]
    # the co-culture and monoculture curves must share the time window: extend the others to 10 h is
    # already true (two-point curves over 0 to 10 h)
    r = interaction_strength(mono_a, mono_b, co, A, B)
    assert r["species_b"]["n_mono"] == 2                     # the spiked replicate did not count
    assert r["species_b"]["mean"] == pytest.approx(-1.5)     # the same as without it
    label, reason = next(s for s in r["skipped"] if "b_spike" in s[0])
    assert label == f"{B}: monoculture replicate b_spike"
    assert "implausible spike" in reason and "at 5 h" in reason
    assert r["flagged"] == [{"species": B, "role": "monoculture", "replicate": "b_spike",
                             "ratio": pytest.approx(1e5), "times": [5.0]}]


def test_a_spiked_curve_is_left_out_for_its_species_only():
    mono_a, mono_b, co = _example()
    co = co + [Replicate([_curve(A, (2, 2)), _spiked(B, 1.0)], "c_spike")]
    r = interaction_strength(mono_a, mono_b, co, A, B)
    assert r["species_a"]["n_co"] == 3       # A's curve in that replicate still counts
    assert r["species_b"]["n_co"] == 2       # B's spiked curve does not


def test_spike_factor_zero_keeps_everything():
    mono_a, mono_b, co = _example()
    mono_b = mono_b + [Replicate([_spiked(B, 1.0)], "b_spike")]
    r = interaction_strength(mono_a, mono_b, co, A, B, spike_factor=0)
    assert r["species_b"]["n_mono"] == 3 and r["flagged"] == []


def test_the_note_about_alternatives_is_carried_into_the_report():
    mono_a, mono_b, co = _example()
    note = "other measurements ...: community fc clean (max/median 3.2)"
    flagged = Replicate([_spiked(B, 1.0)], "b_spike", {B: note})
    r = interaction_strength(mono_a, mono_b + [flagged], co, A, B)
    reason = dict(r["skipped"])[f"{B}: monoculture replicate b_spike"]
    assert reason.endswith("community fc clean (max/median 3.2)")
