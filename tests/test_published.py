

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
