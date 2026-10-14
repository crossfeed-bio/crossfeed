"""The study-level tripwire for growth rates (#173): a study slow as a block is named, never refused."""
from grownet import matrix
from grownet.report import report_text


def _rates(**studies):
    """One organism per value, so a study's values can sit on different organisms, as they do live."""
    out = {}
    for sid, values in studies.items():
        for i, v in enumerate(values):
            out[f"{sid}-{i}"] = {"name": f"{sid} organism {i}", "rate": v, "unit": "1/h", "per_study": {sid: v}}
    return out


def test_a_study_slow_as_a_block_is_named():
    """#173's case, with Craig's agent's study grouping: four organisms of one study, all five to fifteen
    times below the rest. The organism grouping says nothing here; the study grouping says exactly this."""
    rates = _rates(S2=[0.25, 0.30], S4=[0.36, 0.68], S7=[0.38, 0.40, 0.26], S18=[0.0147, 0.0200, 0.0233, 0.0412])
    (slow,) = matrix.slow_studies(rates)
    assert slow["study"] == "S18" and slow["rates"] == 4 and slow["fastest"] == 0.0412
    assert slow["factor"] > matrix.SLOW_FACTOR


def test_one_fast_rate_in_the_study_keeps_it_unflagged():
    """As a BLOCK: a study with one rate in the ordinary range is not slow, however slow the rest."""
    # three slow and one ordinary: a median would call the study slow, its fastest rate does not
    rates = _rates(S2=[0.25, 0.30], S4=[0.36, 0.68], S7=[0.38, 0.40], S18=[0.0147, 0.015, 0.016, 0.30])
    assert matrix.slow_studies(rates) == []


def test_too_few_other_studies_say_nothing():
    rates = _rates(S2=[0.25], S4=[0.36], S18=[0.0147])
    assert matrix.slow_studies(rates) == [], "two other studies are not a reference"


def test_the_report_names_it_and_the_meta_carries_it():
    from grownet.mgrowthdb import records_to_network
    net = records_to_network([])
    rates = _rates(S2=[0.25, 0.30], S4=[0.36, 0.68], S7=[0.38, 0.40], S18=[0.0147, 0.0412])
    net.meta["growth_rates"] = matrix.rate_meta(net, rates, "easylinear")
    assert [s["study"] for s in net.meta["growth_rates"]["slow_studies"]] == ["S18"]
    text = report_text({"network": net, "errors": [], "skipped": [], "resolved": [], "unresolved": [],
                        "studies": ["S2", "S4", "S7", "S18"]})
    assert "slow as a block: every rate from S18 (2, the fastest 0.0412)" in text


def test_a_large_study_does_not_set_every_other_study_s_reference():
    """Craig's agent, on #287: pooling rates let a study that gave twenty of them set the median every other
    study is tested against. One study, one vote."""
    big_slow = [0.03] * 20
    rates = _rates(S1=[0.30, 0.32], S2=[0.28, 0.31], S3=[0.33, 0.29], S4=[0.05, 0.055], BIG=big_slow)
    # pooled, the twenty slow rates would put the reference near 0.03 and S4 would look fast; per study,
    # the reference is the median of five study medians and S4's 0.055 is 5.5 times below it
    flagged = {s["study"] for s in matrix.slow_studies(rates)}
    assert "S4" in flagged and "BIG" in flagged, flagged
