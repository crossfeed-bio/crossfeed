"""Why the daily All network was not served, said where a reader sees it (#157), and the notes of a search
reaching the report and the command line, not only the page."""
import datetime
import io
import json

from test_gui import FakeClient

from grownet import published
from grownet.gui import run_query
from grownet.report import report_text


def _payload(**meta):
    live = run_query(FakeClient(), [], {}, all_studies=True, published=False)
    payload = json.loads(json.dumps(published.to_payload(live)))
    payload["network"]["meta"].update(meta)
    return payload


def _opener(payload):
    return lambda url, timeout: io.BytesIO(json.dumps(payload).encode())


def test_each_reason_a_file_is_not_served_is_named():
    p = _payload()
    derived = datetime.datetime.fromisoformat(p["network"]["meta"]["derived_at"])
    soon = derived + datetime.timedelta(hours=1)
    assert published.why_not_fresh(p, soon) is None and published.fresh(p, soon)
    old = derived + published.MAX_AGE + datetime.timedelta(hours=2)
    assert "hours old" in published.why_not_fresh(p, old) and not published.fresh(p, old)
    assert "in the future" in published.why_not_fresh(p, derived - datetime.timedelta(hours=1))
    assert "format" in published.why_not_fresh({**p, "format": "grownet.all_result/v0"}, soon)
    other = "integrated" if p["network"]["meta"]["settings"]["derivation"] != "integrated" else "replicate"
    assert "derivation" in published.why_not_fresh(p, soon, {"derivation": other})
    no_time = json.loads(json.dumps(p))
    del no_time["network"]["meta"]["derived_at"]
    assert "no time" in published.why_not_fresh(no_time, soon)


def test_a_defect_in_reading_is_told_apart_from_a_stale_file():
    """The broad `except` kept the fallback and hid the cause: a bug in `from_payload` and an old file both
    returned None with nothing to say which (#157)."""
    p = _payload()
    now = datetime.datetime.fromisoformat(p["network"]["meta"]["derived_at"]) + datetime.timedelta(hours=1)
    broken = json.loads(json.dumps(p))
    broken["network"]["edges"] = "not a list"                         # read by from_payload, which raises
    why = []
    assert published.fetch_from(_opener(broken), now=now, why=why) is None
    assert why and "could not be read" in why[0] and "defect" in why[0]

    def offline(url, timeout):
        raise OSError("no route to host")
    why = []
    assert published.fetch_from(offline, now=now, why=why) is None
    assert "could not be fetched from GitHub (OSError: no route to host)" in why[0]

    why = []
    assert published.fetch_from(_opener(p), now=now, why=why) is not None and why == []


def test_the_reason_reaches_the_page_the_report_and_the_command_line(monkeypatch, capsys):
    monkeypatch.setattr(published, "fetch",
                        lambda settings=None, why=None: (why.append("it is 40 hours old") if why is not None
                                                         else None))
    r = run_query(FakeClient(), [], {}, all_studies=True)
    note = "the network derived once a day in the grownet repository was not used, so All was derived live"
    assert any(n.startswith(note) and n.endswith("it is 40 hours old") for n in r["notes"]), r["notes"]
    assert f"note: {note}: it is 40 hours old" in report_text(r)


def test_a_search_s_notes_reach_the_command_line(monkeypatch, capsys):
    """`notes` reached the page only: neither the report nor `derive --species` printed them, so a value in
    Exclude these studies that excluded nothing was said on the page and nowhere else."""
    import os

    from grownet import __main__ as cli
    from grownet import gui
    real = gui.run_query
    monkeypatch.setattr(gui, "run_query", lambda *a, **k: {**real(FakeClient(), ["853"], {}),
                                                         "notes": ["not used in Exclude these studies: S9"]})
    monkeypatch.setattr(cli, "MGrowthDBClient", lambda *a, **k: object(), raising=False)
    args = cli.build_parser().parse_args(["derive", "--live", "--species", "A", "--out", os.devnull])
    cli._derive_species(args)
    assert "note: not used in Exclude these studies: S9" in capsys.readouterr().err
