

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
