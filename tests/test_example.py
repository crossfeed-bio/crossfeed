"""The runnable example and the CLI's custom-Deriver loading stay working (so the docs cannot rot)."""
import pytest

from crossfeed.__main__ import _load_deriver


def test_example_builds_valid_network():
    from examples.custom_deriver import build_example_network
    net = build_example_network()
    assert net.validate() == []
    assert len(net.edges) >= 1


def test_load_deriver_resolves_class():
    d = _load_deriver("examples.custom_deriver:RelativeChangeDeriver")
    assert d.name == "relative-change-example"
    # it satisfies the Deriver contract
    records, skipped = d.derive({"id": "S"}, [])
    assert records == [] and skipped == []


def test_load_deriver_bad_spec():
    with pytest.raises(SystemExit):
        _load_deriver("no_colon_here")


def test_load_deriver_missing_class():
    with pytest.raises(SystemExit):
        _load_deriver("examples.custom_deriver:NoSuchClass")
