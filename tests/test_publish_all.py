"""The daily All artifact's publisher: what it refuses to publish, and what it says about what it does (#236)."""
import datetime
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packaging"))
import publish_all  # noqa: E402
from publish_all import floor, previous_arcs, release_notes  # noqa: E402

from grownet.model import InteractionNetwork  # noqa: E402
from grownet.published import FILE, MAX_AGE  # noqa: E402


def test_a_collapsed_derivation_is_not_published():
    """The workflow gated on `result["errors"]` alone, so zero arcs published, passed `fresh`, and was
    served to every reader at the defaults, under a description saying every arc cites its studies."""
    assert floor(0, None) and floor(0, 145) and floor(0, 145, allow_drop=True), "zero is never published"
    assert floor(145, None) == [] and floor(145, 145) == [] and floor(12, None) == []


def test_a_fall_below_half_of_the_previous_artifact_needs_saying_so():
    refused = floor(70, 145)
    assert refused and "70 arcs" in refused[0] and "145" in refused[0] and "allow_drop" in refused[0]
    assert floor(70, 145, allow_drop=True) == [], "a run by hand can say the drop is meant"
    assert floor(73, 145) == [], "half or more is a data update, not a collapse"
    # growth is never refused: the default went from 12 arcs to 145 on 2026-10-10
    assert floor(145, 12) == []


def test_an_unreadable_previous_artifact_compares_with_nothing():
    def fails(url, timeout):
        raise OSError("offline")
    assert previous_arcs(fails) is None
    assert floor(5, previous_arcs(fails)) == [], "only the zero floor applies then"

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    body = json.dumps({"network": {"edges": [{}, {}, {}]}}).encode()
    assert previous_arcs(lambda url, timeout: Response(body)) == 3


def _result():
    net = InteractionNetwork(meta={"derived_at": "2026-10-12T10:03:41+00:00", "tool_version": "0.4.0",
                                   "settings": {"derivation": "replicate"}})
    return {"network": net, "studies": ["S1", "S2"]}


def test_the_release_description_says_what_this_run_produced_and_what_each_file_promises():
    """It was written once, on the first run, so it could not be corrected by editing the workflow, and it
    promised "the default settings" for two files nothing checks against a reader's version (#236)."""
    notes = release_notes(_result())
    for asset in (FILE, publish_all.NETWORK, publish_all.REPORT):
        assert f"`{asset}`" in notes, f"{asset} is uploaded and not described"
    assert "2026-10-12T10:03:41+00:00" in notes and "grownet 0.4.0" in notes and "`replicate`" in notes
    assert "Nothing checks these two" in notes
    # the age it states is the age `fresh` applies, whatever MAX_AGE is set to
    assert publish_all._age(MAX_AGE) in notes
    assert publish_all._age(datetime.timedelta(days=1)) == "less than a day old"
    assert publish_all._age(datetime.timedelta(hours=30)) == "less than 30 hours old"


def test_the_workflow_sets_the_description_on_every_run():
    import pytest
    path = ROOT / ".github" / "workflows" / "all-network.yml"
    if not path.exists():
        # the sdist carries the publisher but not the repository's workflows, which are not part of what
        # a packager builds; the check runs wherever the workflow is, which is every CI job but `package`
        pytest.skip("no .github in this tree (an unpacked sdist)")
    wf = path.read_text(encoding="utf-8")
    assert "publish_all.py out notes.md" in wf
    assert "gh release edit all-network --notes-file notes.md" in wf
    assert '--notes "' not in wf, "a literal description behind `||` is written once and never again"
    assert "ALLOW_DROP: ${{ inputs.allow_drop }}" in wf


def test_main_publishes_nothing_when_the_floor_refuses(tmp_path, monkeypatch):
    monkeypatch.setattr(publish_all, "run_query", lambda *a, **k: {**_result(), "errors": []})
    monkeypatch.delenv("ALLOW_DROP", raising=False)
    out = tmp_path / "out"
    assert publish_all.main(str(out), str(tmp_path / "notes.md"), previous=lambda: 145) == 1
    assert not out.exists() and not (tmp_path / "notes.md").exists()


def test_main_publishes_a_run_the_floor_allows_and_the_notes_are_not_an_asset(tmp_path, monkeypatch):
    """The positive control for the refusal above: the same run, with an arc, is published."""
    from test_gui import FakeClient

    from grownet.gui import run_query
    monkeypatch.setattr(publish_all, "run_query", lambda *a, **k: run_query(
        FakeClient(), [], dict(publish_all.DEFAULTS), all_studies=True, published=False))
    out = tmp_path / "out"
    assert publish_all.main(str(out), str(tmp_path / "notes.md"), previous=lambda: None) == 0
    assert sorted(p.name for p in out.iterdir()) == sorted([FILE, publish_all.NETWORK, publish_all.REPORT])
    assert "This run:" in (tmp_path / "notes.md").read_text(encoding="utf-8")
