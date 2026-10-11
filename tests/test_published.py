

def test_a_broken_payload_falls_back_to_a_live_derivation():
    """#155 item 14. The guard covered the fetch and the JSON parse, while the TypeError its own comment
    describes comes from `from_payload`, which sat outside it along with `fresh`. An artifact this copy
    cannot read is a reason to derive live, which is what the guard is for, so every step of reading it
    has to be inside."""
    import contextlib
    import io
    import json

    from grownet import published

    @contextlib.contextmanager
    def opener(url, timeout=None):
        # fresh enough and the right format and schema, so `fresh` passes and `from_payload` is reached,
        # but the network is not a document the model can read
        from grownet.mgrowthdb import provenance
        from grownet.model import SCHEMA
        payload = {"format": published.FORMAT,
                   "network": {"schema": SCHEMA, "nodes": "not a list", "edges": [], "studies": [],
                               "meta": provenance()}}
        yield io.BytesIO(json.dumps(payload).encode("utf-8"))

    assert published.fetch_from(opener) is None


def test_a_published_network_derived_the_other_way_is_not_served():
    """The schema id cannot see which derivation filled the fields: a format id moves when a FIELD changes
    meaning, and the derivation is not a field. So the artifact and a live run can carry the same format,
    the same schema, and entirely different networks.

    That is not hypothetical. On 2026-10-10 the default went back to the comparison of replicate sets
    while the published artifact was still the integrated form's: 12 arcs against 145 on the same corpus,
    `fresh()` true, and nothing between a reader asking for the default and a network made the other way.
    """
    import contextlib
    import datetime
    import io
    import json

    from grownet import published
    from grownet.mgrowthdb import provenance
    from grownet.model import SCHEMA

    def serving(derivation):
        @contextlib.contextmanager
        def opener(url, timeout=None):
            meta = provenance()
            meta["derived_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            meta["settings"] = {"derivation": derivation}
            payload = {"format": published.FORMAT,
                       "network": {"schema": SCHEMA, "nodes": [], "edges": [], "studies": [],
                                   "meta": meta},
                       "resolved": [], "skipped": []}
            yield io.BytesIO(json.dumps(payload).encode("utf-8"))
        return opener

    # the artifact says which form made it, and the reader says which they want
    assert published.fetch_from(serving("integrated"), settings={"derivation": "integrated"}) is not None
    assert published.fetch_from(serving("replicate"), settings={"derivation": "replicate"}) is not None
    assert published.fetch_from(serving("integrated"), settings={"derivation": "replicate"}) is None
    assert published.fetch_from(serving("replicate"), settings={"derivation": "integrated"}) is None

    # an artifact from before the field existed is still served: it is the age and the schema that
    # protect those, and refusing them all would turn every old artifact into a live corpus derivation
    @contextlib.contextmanager
    def no_settings(url, timeout=None):
        meta = provenance()
        meta["derived_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        payload = {"format": published.FORMAT,
                   "network": {"schema": SCHEMA, "nodes": [], "edges": [], "studies": [], "meta": meta},
                   "resolved": [], "skipped": []}
        yield io.BytesIO(json.dumps(payload).encode("utf-8"))

    assert published.fetch_from(no_settings, settings={"derivation": "replicate"}) is not None


def test_the_artifact_carries_the_arcs_the_threshold_left_out():
    """The module says the file holds the whole result of the search. It dropped `absent`, `rates` and
    `steady`, so the published artifact's report stated "78 below the absence threshold" and its page
    section listed none of them, while the CLI's message for that condition says "The report lists them"
    (#228, measured live 2026-10-11).

    `absent` is a network of its own, which is why it was lost: the other fields pass through as JSON and
    it needs serializing the way `network` does.
    """
    import json

    from grownet import published
    from grownet.mgrowthdb import records_to_network

    def arc(source, target, strength, status):
        return {"source": source, "target": target, "source_name": source.upper(),
                "target_name": target.upper(), "effect": "facilitation", "strength": strength,
                "weight": abs(strength), "status": status, "outcome": "quantified", "study_id": "S1"}

    result = {"network": records_to_network([arc("a", "b", 1.0, "present")]),
              "absent": records_to_network([arc("c", "d", 0.01, "absent")]),
              "rates": {"a": {"name": "A", "rate": 0.5, "unit": "1/h"}},
              "steady": [{"study": "S1", "satisfied": True}],
              "absence": {"k": 1.0, "absent": 1}, "hidden": {"absent": 1},
              "entries": [], "settings": {}, "studies": [], "skipped": [], "errors": []}

    back = published.from_payload(json.loads(json.dumps(published.to_payload(result))))

    assert back["absent"] is not None, "the arcs the threshold left out are missing from the artifact"
    assert [(e.source, e.target) for e in back["absent"].edges] == [("c", "d")]
    assert back["absent"].edges[0].status == "absent"
    assert back["rates"] == result["rates"]
    assert back["steady"] == result["steady"]
    # and the network itself is still the network, not the absent one
    assert [(e.source, e.target) for e in back["network"].edges] == [("a", "b")]
    # an artifact written before this carried no `absent` key at all, and must still load
    older = json.loads(json.dumps(published.to_payload(result)))
    older.pop("absent")
    assert published.from_payload(older)["absent"] is None


def test_every_field_a_search_returns_is_carried_or_deliberately_left_out():
    """`FIELDS` is the module's claim to hold the whole result, so it is checked against what
    `run_query` actually returns rather than maintained by hand: three keys were missing and the loss was
    silent (#228).

    A key that is deliberately not carried is named here with the reason, so the next one added to
    `run_query` fails this test rather than disappearing.
    """
    import inspect
    import re

    from grownet import gui, published

    returned = set(re.findall(r'"([a-z_]+)":', inspect.getsource(gui.run_query).split("return {", 1)[1]))
    carried = set(published.FIELDS) | {"network", "absent"}
    # Nothing is deliberately left out today, so this set is empty and the check is strict. A key that
    # genuinely should not travel goes here WITH its reason, and the next key added to `run_query`
    # then fails this test rather than disappearing from the artifact in silence.
    deliberate = set()
    missing = returned - carried - deliberate
    assert not missing, (
        f"run_query returns these and the artifact drops them silently: {sorted(missing)}. Carry them in "
        "FIELDS, or name them above with the reason they are not carried.")
    # and the probe is not looking at nothing, which would make the assertion vacuous
    assert len(returned) > 15, returned
    assert {"network", "absent", "rates", "steady", "notes"} <= returned
