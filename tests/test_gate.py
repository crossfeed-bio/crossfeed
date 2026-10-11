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


def test_the_secrets_pattern_does_not_require_the_value_to_be_quoted(monkeypatch):
    """The pattern required quotes around the value until 2026-10-11, so the way a secret is most likely
    to be written in this repository went straight through: a workflow `env:` block is unquoted YAML, and
    so is `TOKEN=...` in a shell line. The tree was clean of secrets throughout, so this was a hole in the
    guard rather than an exposure, and `check_secrets` had no test of any kind.

    Both halves matter and both are asserted: what must be caught, and what must not be, since a pattern
    that flags this project's own `${{ secrets.GITHUB_TOKEN }}` is a pattern someone turns off. A
    placeholder is safe because it either starts outside the character class or is shorter than the
    16-character minimum.

    Every example is assembled at run time from pieces. Writing them out would put secret-shaped lines in
    a tracked file and the gate would flag THIS file, which it did on the first attempt: the guard works,
    and a test of a guard must not trip it.
    """
    value = "ghp_" + "0123456789abcdef" + "ghijklmnop"
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    aws = "AKIA" + "IOSFODNN7EXAMPLE"

    def line(keyword, sep, val, quote=""):
        return f"{keyword}{sep}{quote}{val}{quote}\n"

    caught = {
        "workflow.yml": "env:\n  " + line("GITHUB_TOKEN", ": ", value),          # unquoted YAML
        "setenv.py": line("MGROWTHDB_TOKEN", "=", value),                        # unquoted assignment
        "notes.md": line("api_key", ": ", aws),
        "header.py": line("Authorization", ": ", "Bearer " + jwt),               # a header, not a pair
        "quoted.py": line("api_key", " = ", aws, quote='"'),                     # what it always caught
        "key.txt": "-----BEGIN " + "OPENSSH PRIVATE KEY" + "-----\n",
        # the forms openssl and gpg actually emit. Three of these were missed while the check's own
        # description says it covers "private keys", and one key header out of seven was probed (found
        # reviewing this change).
        "rsa.txt": "-----BEGIN " + "RSA PRIVATE KEY" + "-----\n",
        "dsa.txt": "-----BEGIN " + "DSA PRIVATE KEY" + "-----\n",
        "enc.txt": "-----BEGIN " + "ENCRYPTED PRIVATE KEY" + "-----\n",
        "pgp.txt": "-----BEGIN " + "PGP PRIVATE KEY BLOCK" + "-----\n",
        "plain.txt": "-----BEGIN " + "PRIVATE KEY" + "-----\n",
        # ONE PER KEYWORD the pattern names. The first version probed `token`, `api_key` and
        # `authorization` only, so `secret` and `password`, half the key/value group, were untested:
        # narrowing the pattern to `(?:api[_-]?key|token)` let an unquoted `password=` line through
        # with this, its only test, green (found reviewing this change).
        "kw_secret.py": line("secret", "=", value),
        "kw_password.py": line("password", ": ", value),
        "kw_dashkey.py": line("api-key", ": ", value),
        "kw_bearer.py": line("bearer", " ", jwt),
    }
    monkeypatch.setattr(gate, "_read", caught.get)
    found = gate.check_secrets(list(caught))
    assert len(found) == len(caught), f"missed one of {list(caught)}: {found}"

    # ONE CASE PER KEYWORD, each using that keyword alone and each asserted on its own. The loop that
    # was here searched the test's OWN fixtures for the keyword, so it could never fail because of a
    # change to the pattern: it only checked that the test had written the word down. `authorization`
    # was untested in fact, because the single case containing it, `header.py`, is matched by the
    # `bearer` alternative: `Bearer` is itself one of the keywords and the match starts there. Dropping
    # `authorization` from the pattern left all 714 tests green while a Basic auth header, the real form
    # with no `Bearer` in it, stopped being caught (found reviewing round 10).
    basic = "QWxhZGRpbjpvcGVuc2VzYW1l" + "MTIzNA=="
    by_keyword = {
        "api_key": ("kw_api_key.py", line("api_key", ": ", aws)),
        "api-key": ("kw_api_dash_key.py", line("api-key", ": ", value)),
        "secret": ("kw_secret2.py", line("secret", "=", value)),
        "token": ("kw_token.py", line("MGROWTHDB_TOKEN", "=", value)),
        "password": ("kw_password2.py", line("password", ": ", value)),
        "authorization": ("kw_authorization.py", line("Authorization", ": ", basic)),
        "bearer": ("kw_bearer2.py", line("bearer", " ", jwt)),
    }
    # the case that went wrong, pinned: `authorization` must be tested by a line with no `bearer` in it,
    # since `bearer` is itself a keyword and would do the matching. (`api_key` and `api-key` are one
    # alternative, `api[_-]?key`, and are both here only to pin the optional separator.)
    assert "bearer" not in by_keyword["authorization"][1].lower()
    monkeypatch.setattr(gate, "_read", {name: text for name, text in by_keyword.values()}.get)
    for keyword, (name, _text) in by_keyword.items():
        assert gate.check_secrets([name]), f"the pattern no longer catches {keyword}"

    clean = {
        "workflow.yml": "env:\n  GH_TOKEN: ${{ github.token }}\n  O: ${{ secrets.GITHUB_TOKEN }}\n",
        "README.md": "Set `token: <your-token-here>` and `password: $PASSWORD` first.\n",
        "empty.py": 'api_key = ""\n',
        "prose.md": "The secret sauce is that the token is short and a password manager helps.\n",
        "curl.md": "curl -H 'Authorization: Bearer <token>' https://example.org\n",
        # ordinary prose. The whitespace-only separator was applied to all seven keywords although it is
        # there for an Authorization header, and one hyphenated word after "secret" or "token" is 16
        # characters of the class, so this project's own house style tripped the gate. A gate someone
        # turns off is worse than none, which this test's docstring already says.
        "prose2.md": ("GitHub secret scanning-and-rotation is covered in SECURITY.md, and the token "
                      "docs/METHOD_NOTES.md describes is not one.\n"),
        "prose3.md": "Use a password manager.Keychain entry, and every secret rotation-and-revocation step.\n",
    }
    monkeypatch.setattr(gate, "_read", clean.get)
    assert gate.check_secrets(list(clean)) == []

    # And a separate thing this test ran into rather than set out to show: the first draft used a
    # `setenv.sh`, and it was not flagged because `.sh` is not in `gate.TEXT_EXT`, so that file is never
    # READ by this check. That is #227 and not the pattern, and it is pinned here so a future failure
    # cannot confuse the two.
    unscanned = {"setenv.sh": line("MGROWTHDB_TOKEN", "=", value)}
    monkeypatch.setattr(gate, "_read", unscanned.get)
    assert gate.check_secrets(list(unscanned)) == [], "if this flags now, #227 is fixed and this is stale"
    assert not any(name.endswith(gate.TEXT_EXT) for name in unscanned)
