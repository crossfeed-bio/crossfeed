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
    assert floor(73, 146) == [] and floor(72, 146), "exactly half publishes, one below refuses"
    # growth is never refused: the default went from 12 arcs to 145 on 2026-10-10
    assert floor(145, 12) == []


def test_an_unreadable_previous_artifact_refuses_and_only_a_404_compares_with_nothing():
    """It failed OPEN: every read failure returned None, which skipped the half check, so a 503 on the
    night a derivation collapsed published the collapse (Craig's agent, on #275). Now only a 404, the
    first run, means there is nothing to compare with."""
    import urllib.error

    def offline(url, timeout):
        raise OSError("offline")

    def missing(url, timeout):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    def unavailable(url, timeout):
        raise urllib.error.HTTPError(url, 503, "Service Unavailable", {}, None)
    assert previous_arcs(missing) is None and floor(5, previous_arcs(missing)) == []
    for opener, says in ((offline, "OSError: offline"), (unavailable, "HTTP 503")):
        waited = []
        reason = previous_arcs(opener, sleep=waited.append)
        assert says in reason, reason
        # read again before the refusal stands, and a bounded number of times
        assert len(waited) == publish_all.READS - 1, waited
        refused = floor(145, reason)
        assert refused and "could not be read" in refused[0] and "allow_drop" in refused[0]
        assert floor(145, reason, allow_drop=True) == [], "a hand run can still publish"

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    body = json.dumps({"network": {"edges": [{}, {}, {}]}}).encode()
    assert previous_arcs(lambda url, timeout: Response(body)) == 3


def test_a_gateway_answer_that_clears_is_read_again_and_one_that_cannot_clear_is_not():
    """One HTTP 504 reading the artifact refused a whole day's publish (run 42471472131 on 2026-11-08),
    and the floor's own advice, "run the workflow again", was carried out by hand six hours later with
    every 0.3.x and 0.4.x copy already deriving All live. The refusal was right and the single read was
    not. So an answer that waiting fixes is read again, and nothing else is."""
    import urllib.error

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    body = json.dumps({"network": {"edges": [{}, {}, {}, {}, {}]}}).encode()
    reads, waited = [], []

    def clears_on_the_third(url, timeout):
        reads.append(url)
        if len(reads) < 3:
            raise urllib.error.HTTPError(url, 504, "Gateway Time-out", {}, None)
        return Response(body)
    assert previous_arcs(clears_on_the_third, sleep=waited.append) == 5, "the day publishes"
    assert len(reads) == 3, reads
    assert waited == [publish_all.BACKOFF, publish_all.BACKOFF ** 2], "and waits longer each time"

    # The other direction, which is what keeps this a transient case and not a blanket retry: a code
    # that waiting does not fix, and a body that parses and is not a network, are each answered on the
    # first read, and each still refuses the publish.
    forbidden = []

    def no_token(url, timeout):
        forbidden.append(url)
        raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
    reason = previous_arcs(no_token, sleep=waited.append)
    assert len(forbidden) == 1 and "HTTP 403" in reason, (forbidden, reason)
    assert floor(145, reason) and "could not be read" in floor(145, reason)[0]

    wrong = []

    def not_a_network(url, timeout):
        wrong.append(url)
        return Response(json.dumps({"nodes": []}).encode())
    reason = previous_arcs(not_a_network, sleep=waited.append)
    assert len(wrong) == 1 and "KeyError" in reason, (wrong, reason)
    assert floor(145, reason), reason


def test_a_body_cut_short_is_read_again_in_both_of_the_forms_it_arrives_in():
    """Karoline's agent, reviewing: "A body cut short usually does not arrive as JSONDecodeError". When
    the server sent a Content-Length and the connection drops partway, `read()` notices the shortfall
    itself and raises http.client.IncompleteRead, which derives from HTTPException and not from
    OSError, so it fell through the retried tuple and refused on the FIRST read. A release asset served
    by the CDN normally carries a length, so that is the likely form of the very case this retry exists
    for. Both forms are now read again.

    Hand computed: each opener fails twice and succeeds on the third read, so the arc count is the 5
    edges of the body, the opener is called 3 times, and 2 waits are taken, of 2.0 and 4.0 seconds."""
    import http.client

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Truncated(Response):
        """A response whose body is cut short AFTER a Content-Length promised more, which is what the
        CDN serves. `read()` raises rather than returning the short bytes."""

        def read(self, *a):
            raise http.client.IncompleteRead(b"{\"network\": {\"ed", 84)

    body = json.dumps({"network": {"edges": [{}, {}, {}, {}, {}]}}).encode()
    # the two forms, in the order the review distinguished them: with a length, read() raises
    # IncompleteRead; without one (chunked or close-delimited) the short bytes reach json.loads
    short = b"{\"network\": {\"ed"
    for cut in (lambda url, timeout: Truncated(), lambda url, timeout: Response(short)):
        reads, waited = [], []

        def clears_on_the_third(url, timeout, cut=cut, reads=reads):
            reads.append(url)
            return cut(url, timeout) if len(reads) < 3 else Response(body)
        assert previous_arcs(clears_on_the_third, sleep=waited.append) == 5, "the day publishes"
        assert len(reads) == 3, reads
        assert waited == [publish_all.BACKOFF, publish_all.BACKOFF ** 2], waited

    # and it still fails closed when every read is cut short, which is the floor this never lifts
    reason = previous_arcs(lambda url, timeout: Truncated(), sleep=lambda s: None)
    assert "IncompleteRead" in reason and f"every one of {publish_all.READS} reads" in reason, reason
    assert floor(145, reason) and "could not be read" in floor(145, reason)[0]


def _result():
    net = InteractionNetwork(meta={"derived_at": "2026-10-12T10:03:41+00:00", "tool_version": "0.4.0",
                                   "settings": {"derivation": "replicate"}})
    return {"network": net, "studies": ["S1", "S2"]}


def test_the_release_description_says_what_this_run_produced_and_what_each_file_promises():
    """It was written once, on the first run, so it could not be corrected by editing the workflow, and it
    promised "the default settings" for two files nothing checks against a reader's version (#236)."""
    notes = release_notes(_result())
    for asset in (FILE, publish_all.LEGACY["file"], publish_all.NETWORK, publish_all.REPORT):
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
    assert sorted(p.name for p in out.iterdir()) == sorted([FILE, publish_all.LEGACY["file"], "all_result.v4.json",
                                                            publish_all.NETWORK, publish_all.REPORT])
    assert "This run:" in (tmp_path / "notes.md").read_text(encoding="utf-8")


def test_the_network_names_the_commit_that_built_it(tmp_path, monkeypatch):
    """Craig's agent, on #285: the daily artifact is built from main under the last release's tool_version,
    so two files a week apart can carry one version and different content. The commit says which."""
    from test_gui import FakeClient

    from grownet.gui import run_query
    from grownet.schema import validate_document
    monkeypatch.setattr(publish_all, "run_query", lambda *a, **k: run_query(
        FakeClient(), [], dict(publish_all.DEFAULTS), all_studies=True, published=False))
    monkeypatch.setenv("GITHUB_SHA", "abc123")
    monkeypatch.setenv("GITHUB_RUN_ID", "42")
    out = tmp_path / "out"
    assert publish_all.main(str(out), None, previous=lambda: None) == 0
    doc = json.loads((out / publish_all.NETWORK).read_text(encoding="utf-8"))
    assert doc["meta"]["build"] == {"commit": "abc123", "run": "42"}
    notes = []
    assert validate_document(doc, notes) == [] and not [n for n in notes if "declare" in n], notes


def test_the_older_format_is_published_beside_the_current_one(tmp_path, monkeypatch):
    """Karoline, 2026-10-12, on #289: "Publish both". Installed 0.3.x and 0.4.x copies fetch
    `all_result.json` and refuse any schema but /v3; /v4 only added fields, so the same artifact with those
    removed is a /v3 document. It must read as /v3 to the reader those copies run."""
    from test_gui import FakeClient

    from grownet import published
    from grownet.gui import run_query
    from grownet.schema import validate_document
    monkeypatch.setattr(publish_all, "run_query", lambda *a, **k: run_query(
        FakeClient(), [], dict(publish_all.DEFAULTS), all_studies=True, published=False))
    out = tmp_path / "out"
    assert publish_all.main(str(out), None, previous=lambda: None) == 0
    assert FILE == "all_result.v5.json"
    current = json.loads((out / FILE).read_text(encoding="utf-8"))
    legacy = json.loads((out / "all_result.json").read_text(encoding="utf-8"))
    assert current["network"]["schema"].endswith("/v5") and legacy["network"]["schema"].endswith("/v3")
    # the /v4 file, which installed 0.5.0 copies read (#305): the same arcs without `technique`, and served
    # by such a copy, its own SCHEMA and the derivation it asks for
    v4 = json.loads((out / "all_result.v4.json").read_text(encoding="utf-8"))
    assert v4["network"]["schema"] == "grownet.interaction_network/v4"
    assert current["network"]["edges"] and all(e.get("technique") for e in current["network"]["edges"])
    assert not any("technique" in e for e in v4["network"]["edges"])
    assert len(v4["network"]["edges"]) == len(current["network"]["edges"])
    with monkeypatch.context() as m:
        m.setattr(published, "SCHEMA", "grownet.interaction_network/v4")
        at = datetime.datetime.fromisoformat(v4["network"]["meta"]["derived_at"]) + datetime.timedelta(hours=1)
        assert published.why_not_fresh(v4, at, publish_all.DEFAULTS) is None
    manifest = json.loads((ROOT / "schema" / "format_fields.json").read_text(encoding="utf-8"))
    v3 = manifest["formats"]["grownet.interaction_network/v3"]
    for kind, key in (("node", "nodes"), ("edge", "edges"), ("study", "studies")):
        for item in legacy["network"][key]:
            assert set(item) <= set(v3[kind]), (kind, set(item) - set(v3[kind]))
    assert len(legacy["network"]["edges"]) == len(current["network"]["edges"])
    # no meta key an installed 0.4.0 does not declare, which its `validate` would note as suspect
    assert set(legacy["network"]["meta"]) <= publish_all.LEGACY_META["grownet.interaction_network/v3"]
    assert {"complete", "errors"} <= set(current["network"]["meta"]), "the current file keeps them"
    notes = []
    assert validate_document(legacy["network"], notes) == []
    # and the identity is the legacy file's own, recomputable from it (it only differed from the current
    # one before, which a constant hash also does; found in review)
    assert legacy["identity"]["content_sha256"] == published._identity(legacy)["content_sha256"]
    assert legacy["identity"]["content_sha256"] != current["identity"]["content_sha256"]
    # read as an installed /v3 copy reads it: its own SCHEMA, and the derivation it asks for
    monkeypatch.setattr(published, "SCHEMA", "grownet.interaction_network/v3")
    derived = datetime.datetime.fromisoformat(legacy["network"]["meta"]["derived_at"])
    assert published.why_not_fresh(legacy, derived + datetime.timedelta(hours=1), publish_all.DEFAULTS) is None


def test_the_first_run_of_a_new_format_compares_with_the_legacy_file():
    """`all_result.v4.json` does not exist before the first /v4 run, so the floor reads the legacy file
    rather than comparing with nothing."""
    import urllib.error

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(url, timeout):
        if url == publish_all.URL:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return Response(json.dumps({"network": {"edges": [{}] * 145}}).encode())
    assert previous_arcs(opener) == 145



def test_every_older_format_from_v3_gets_its_own_file():
    """Found in review: one hard-coded legacy entry meant that at /v5 nothing would write
    `all_result.v4.json`, and every installed /v4 copy would derive All live. Every format id from /v3 to
    the one before the current gets a file, read from the manifest."""
    manifest = json.loads((ROOT / "schema" / "format_fields.json").read_text(encoding="utf-8"))
    # at /v5 (#305) exactly what this test was written to foresee: the /v4 readers get their file
    assert publish_all.older_formats(manifest) == ["grownet.interaction_network/v3", "grownet.interaction_network/v4"]
    assert publish_all.file_for("grownet.interaction_network/v3") == "all_result.json"
    assert publish_all.file_for("grownet.interaction_network/v4") == "all_result.v4.json"
    later = {**manifest, "formats": {**manifest["formats"], "grownet.interaction_network/v6":
                                     manifest["formats"]["grownet.interaction_network/v5"]},
             "current": "grownet.interaction_network/v6"}
    assert publish_all.older_formats(later) == ["grownet.interaction_network/v3", "grownet.interaction_network/v4",
                                                "grownet.interaction_network/v5"]
    assert publish_all.file_for("grownet.interaction_network/v5") == "all_result.v5.json"


def test_the_arcs_below_the_threshold_are_written_in_the_older_format_too():
    """The fake search has no absent network, so stripping it was never exercised (found in review)."""
    payload = {"format": "grownet.all_result/v1",
               "network": {"schema": "grownet.interaction_network/v4", "meta": {"tool": "grownet", "build": {}},
                           "nodes": [{"id": "a", "taxon_id_refused": "x"}], "studies": [{"id": "S1"}],
                           "edges": [{"source": "a", "target": "a", "effect": "facilitation", "window": 3.0}]}}
    payload["absent"] = json.loads(json.dumps(payload["network"]))
    legacy = publish_all.legacy_payload(payload)
    for part in ("network", "absent"):
        assert legacy[part]["schema"] == "grownet.interaction_network/v3"
        assert "window" not in legacy[part]["edges"][0] and "taxon_id_refused" not in legacy[part]["nodes"][0]
        assert "build" not in legacy[part]["meta"] and legacy[part]["meta"]["tool"] == "grownet"


def test_with_both_result_files_gone_the_floor_reads_all_network_json():
    """The emergency procedure deletes both result files and leaves all_network.json; the floor then
    compares with it rather than treating the night as a first run. Nothing tested it (found in review)."""
    import urllib.error

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(url, timeout):
        if url.endswith(publish_all.NETWORK):
            return Response(json.dumps({"schema": "x", "edges": [{}] * 140}).encode())
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
    assert previous_arcs(opener) == 140


def test_an_older_format_that_lost_a_field_is_refused_and_every_real_one_writes():
    """The subset refusal and the real manifest: every format from /v3 to the current can be written, so a
    format move that drops a field fails here, in CI, not at 03:17 after a whole derivation (found in review)."""
    import pytest
    manifest = json.loads((ROOT / "schema" / "format_fields.json").read_text(encoding="utf-8"))
    payload = {"format": "grownet.all_result/v1",
               "network": {"schema": manifest["current"], "meta": {}, "nodes": [], "edges": [], "studies": []}}
    for schema in publish_all.older_formats(manifest):
        assert publish_all.legacy_payload(payload, schema)["network"]["schema"] == schema
        assert schema in publish_all.LEGACY_META, f"no meta snapshot for {schema}"
    assert manifest["current"] in publish_all.LEGACY_META, "the snapshot for the format that will be older next"
    # no released format ever lost a field, so the refusal is shown on a manifest where one did
    fake_root = Path(__import__("tempfile").mkdtemp())
    (fake_root / "schema").mkdir()
    dropped = json.loads(json.dumps(manifest))
    dropped["formats"]["grownet.interaction_network/v3"]["edge"].append("a_field_v4_removed")
    (fake_root / "schema" / "format_fields.json").write_text(json.dumps(dropped))
    original = publish_all.ROOT
    try:
        publish_all.ROOT = fake_root
        with pytest.raises(ValueError, match="no longer has"):
            publish_all.legacy_payload(payload, "grownet.interaction_network/v3")
    finally:
        publish_all.ROOT = original



def test_the_legacy_meta_keys_are_0_4_0_s_own():
    """Round 2 of the review: the test compared the legacy file with LEGACY_META itself, so a key added to
    the constant survived. 0.4.0's META_PROPERTIES, pinned (git show v0.4.0:src/grownet/schema.py)."""
    assert publish_all.LEGACY_META["grownet.interaction_network/v3"] == {
        "absence", "data", "derived_at", "derived_on", "filters", "genus", "growth_rates", "hidden", "merge",
        "no_growth", "provisional", "query", "selection", "settings", "source_db", "species", "statistics",
        "studies", "study_id", "tool", "tool_version"}


def test_the_current_format_s_meta_snapshot_is_the_schema_s_while_it_is_current():
    """Round 3 of the review: nothing tied the snapshot to the schema, so a meta key added before the next
    move would leave the snapshot short of what the format's files held, and a legacy copy would strip it."""
    from grownet.schema import META_PROPERTIES
    manifest = json.loads((ROOT / "schema" / "format_fields.json").read_text(encoding="utf-8"))
    assert publish_all.LEGACY_META[manifest["current"]] == set(META_PROPERTIES)


def test_the_release_notes_name_the_commit_and_claim_nothing_more(monkeypatch):
    # GitHub Actions sets GITHUB_REF_NAME on every job (the tag in release.yml, `<n>/merge` on a pull
    # request), so the test sets it itself: reading the runner's made the tag job fail (found in review)
    monkeypatch.delenv("GITHUB_REF_NAME", raising=False)
    result = _result()
    result["network"].meta["build"] = {"commit": "abc1234def", "run": "9"}
    notes = release_notes(result)
    assert "as of commit abc1234 of main" in notes and "unreleased" not in notes
    monkeypatch.setenv("GITHUB_REF_NAME", "some-branch")
    assert "as of commit abc1234 of some-branch" in release_notes(result), "a hand run from another branch"


def test_the_release_notes_name_every_older_file(monkeypatch):
    """Round 5 of the review: the description named the one LEGACY file, while a file is written for every
    older format, so from /v5 on the /v4 file would go undescribed."""
    monkeypatch.setattr(publish_all, "older_formats", lambda manifest=None: [
        "grownet.interaction_network/v3", "grownet.interaction_network/v4"])
    notes = release_notes(_result())
    assert "`all_result.json` is the same network for copies that read the older `grownet.interaction_network/v3`" \
        in notes
    assert "`all_result.v4.json` is the same network for copies that read the older " \
        "`grownet.interaction_network/v4`" in notes


def test_an_older_file_is_written_only_in_the_result_format_its_readers_accept():
    """Round 6 of the review: the strip kept the current result format, so the day `published.FORMAT`
    moves every 0.3.x and 0.4.x copy would refuse its file and derive All live, with every check green."""
    import pytest
    payload = {"format": "grownet.all_result/v2",
               "network": {"schema": "grownet.interaction_network/v4", "meta": {}, "nodes": [], "edges": [],
                           "studies": []}}
    with pytest.raises(ValueError, match="accept 'grownet.all_result/v1'"):
        publish_all.legacy_payload(payload, "grownet.interaction_network/v3")
    assert publish_all.legacy_payload({**payload, "format": "grownet.all_result/v1"},
                                      "grownet.interaction_network/v3")["format"] == "grownet.all_result/v1"


def test_an_older_file_is_written_only_with_the_derivation_its_readers_ask_for():
    """Round 7 of the review: the first move of the default derivation would make every installed copy
    refuse its older file (0.4.0's DEFAULTS ask for replicate), with every check green."""
    import pytest
    meta = {"settings": {"derivation": "integrated"}}
    payload = {"format": "grownet.all_result/v1",
               "network": {"schema": "grownet.interaction_network/v4", "meta": meta, "nodes": [], "edges": [],
                           "studies": []}}
    with pytest.raises(ValueError, match="derivation is 'integrated' and readers of grownet.interaction_network/v3"):
        publish_all.legacy_payload(payload, "grownet.interaction_network/v3")
    meta["settings"]["derivation"] = "replicate"
    assert publish_all.legacy_payload(payload, "grownet.interaction_network/v3")["format"] == "grownet.all_result/v1"
    meta.pop("settings")                                   # recording none, it is served
    assert publish_all.legacy_payload(payload, "grownet.interaction_network/v3")["format"] == "grownet.all_result/v1"


def test_the_readers_of_the_current_format_are_this_version_while_it_is_current():
    """Round 8 of the review: nothing checked the /v4 entry, which is read only after the next move, so a
    change of the result format or the default derivation before then would leave it describing readers
    that never existed. While /v4 is current its readers are this version."""
    from grownet import gui, published
    manifest = json.loads((ROOT / "schema" / "format_fields.json").read_text(encoding="utf-8"))
    assert publish_all.READERS[manifest["current"]] == {"format": published.FORMAT,
                                                        "derivation": gui.DEFAULTS["derivation"]}


def test_an_older_file_without_a_result_format_is_not_written():
    """Round 8 of the review: 0.4.0 refuses a file with no format, and the strip accepted one."""
    import pytest
    payload = {"network": {"schema": "grownet.interaction_network/v4", "meta": {}, "nodes": [], "edges": [],
                           "studies": []}}
    with pytest.raises(ValueError, match="format is None"):
        publish_all.legacy_payload(payload, "grownet.interaction_network/v3")


def test_the_strip_judges_by_the_readers_even_after_the_default_moves(monkeypatch):
    """Round 8 of the review: with the default at replicate, judging the strip by today's DEFAULTS rather
    than by the readers' table could not be told apart. Moved to integrated, an integrated payload is still
    refused for the /v3 readers, whose defaults ask for replicate."""
    import pytest

    from grownet import gui
    monkeypatch.setitem(gui.DEFAULTS, "derivation", "integrated")
    payload = {"format": "grownet.all_result/v1",
               "network": {"schema": "grownet.interaction_network/v4",
                           "meta": {"settings": {"derivation": "integrated"}}, "nodes": [], "edges": [], "studies": []}}
    with pytest.raises(ValueError, match="derivation is 'integrated' and readers"):
        publish_all.legacy_payload(payload, "grownet.interaction_network/v3")


def test_the_r_check_refuses_a_skipped_test_in_ci_and_in_make():
    """Round 11 of the review: deleting either `SKIP 0` guard passed the suite, which is how the listener's
    test stayed skipped and failing from #120 on. The R check says OK over a skipped test."""
    import pytest
    workflow, makefile = ROOT / ".github" / "workflows" / "ci.yml", ROOT / "Makefile"
    if not workflow.exists() or not makefile.exists():
        pytest.skip("no .github or Makefile in this tree (an unpacked sdist)")
    ci = workflow.read_text(encoding="utf-8")
    job = ci[ci.index("  r-package:"):]
    job = job[:job.index("\n  windows-app:")] if "\n  windows-app:" in job else job
    assert 'NOT_CRAN: "true"' in job and "grep -q 'SKIP 0 |' grownet.Rcheck/tests/testthat.Rout" in job
    recipe = makefile.read_text(encoding="utf-8").split("r-check:", 1)[1].split("\n\n", 1)[0]
    assert "NOT_CRAN=true R CMD check" in recipe
    assert "grep -q 'SKIP 0 |' grownet.Rcheck/tests/testthat.Rout" in recipe
