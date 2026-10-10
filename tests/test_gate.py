"""The gate's own checks: the merge-marker one, and which deriver a sentence claims is the default."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "checks"))
import gate  # noqa: E402


def test_conflict_markers_are_found_and_a_heading_underline_is_not(monkeypatch):
    files = {"CHANGELOG.md": "# Changes\n<<<<<<< HEAD\n- ours\n=======\n- theirs\n>>>>>>> origin/branch\n",
             "README.txt": "grownet\n=======\n\nStart it\n--------\n"}
    monkeypatch.setattr(gate, "_read", files.get)
    assert gate.check_merge_markers(list(files)) == [
        "conflict marker left from a merge in CHANGELOG.md, line 2",
        "conflict marker left from a merge in CHANGELOG.md, line 6"]


def test_the_claims_gate_names_the_deriver_a_sentence_is_about(tmp_path, monkeypatch):
    """`check_default_deriver` had no test of any kind, before or after its attribution rule was rewritten
    (pointed out reviewing #199, 2026-10-10). The rewrite was needed, because the gate read every deriver
    named within 200 characters as the subject of a phrase like "is the default", which made the one
    sentence a reader now needs, naming both forms and their jobs, unwritable. It also narrowed what the
    gate flags, and nothing pinned the difference.

    These are the shapes that matter, run against a tree built here rather than against the repository,
    so this says what the rule does rather than what today's documents happen to contain.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "checks"))
    import claims_check

    (tmp_path / "src" / "grownet").mkdir(parents=True)
    (tmp_path / "src" / "grownet" / "derive.py").write_text(
        "class ReplicateDeriver:\n    pass\n\n\n"
        "def derive_interactions(deriver=None):\n    return (deriver or ReplicateDeriver()).derive()\n",
        encoding="utf-8")
    (tmp_path / "src" / "grownet" / "integrated.py").write_text(
        "class IntegratedDeriver:\n    pass\n", encoding="utf-8")
    (tmp_path / "src" / "grownet" / "gui.py").write_text(
        'DEFAULTS = {"derivation": "replicate"}\n', encoding="utf-8")
    for name in claims_check.DOCS:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    monkeypatch.setattr(claims_check, "ROOT", str(tmp_path))
    assert claims_check.default_deriver() == "ReplicateDeriver"

    def flagged(readme: str) -> bool:
        (tmp_path / "README.md").write_text(readme, encoding="utf-8")
        found = []
        claims_check.check_default_deriver(found)
        return any("README.md" in p for p in found)

    # the retired one called the default
    assert flagged("`IntegratedDeriver` is the default.")
    # the shipped one called the default
    assert not flagged("`ReplicateDeriver` is the default.")
    # both named, each given its job: the sentence the rewrite exists to allow
    assert not flagged("`ReplicateDeriver` is the default, and `IntegratedDeriver` is what gLV mode "
                       "selects.")
    # named by the flag a reader types rather than by the class: a claim about the derivation is a claim
    # about the deriver, whatever spelling it uses
    assert flagged("**The default derivation.** `--derivation integrated`, which is what runs unless the "
                   "Derivation setting is changed.")

    # THE KNOWN HOLE, recorded so a change to it is visible rather than silent: nearest-mention uses text
    # distance as a proxy for the grammatical subject, which is right for the sentence above and wrong for
    # an appositive, where the retired deriver is the subject and the shipped one sits nearer the phrase.
    # The rule this replaced flagged it, by attributing a claim to every deriver in range; that rule could
    # not express "A is the default, B is not" at all (Craig's agent on #199, 2026-10-10).
    assert not flagged("`IntegratedDeriver`, which `ReplicateDeriver` now follows, is the default.")

    # and when no document names the shipped one at all, the gate says so rather than passing
    (tmp_path / "README.md").write_text("nothing about derivations here", encoding="utf-8")
    missing = []
    claims_check.check_default_deriver(missing)
    assert any("no doc in" in p for p in missing)
