# Releasing

Written by Claude (Karoline's agent) for the maintainers. How a version of the tool reaches its users: on
PyPI (`uv tool install grownet`, `pipx install grownet`) and as a self-contained Windows program attached to
the GitHub release. The `uvx --from git+...` route in the README needs no release; it always runs `main`.

Everything is automated by `.github/workflows/release.yml`, which runs when a version tag is pushed. The CI
jobs `package` and `windows-app` build and start the same artifacts on every push, so a release only
repeats what CI has already shown to work.

## Order for the first release (0.1.0)

1. #79 is reviewed and merged.
2. The rename pull request (#71): the package, the module and the command become `grownet`, Karoline's
   choice. It proposes whether `crossfeed` stays as a second command for a while; the schema id is Craig's
   call. The release workflow's `install` job then starts `grownet` instead of `crossfeed`.
3. The one-time setup below.
4. The release pull request, then the tag (below).

## One-time setup (a maintainer, in a browser)

No password or token is ever stored in the repository or in GitHub secrets: PyPI trusts the release
workflow's short-lived GitHub identity instead ("trusted publishing").

1. **PyPI account.** Sign in at <https://pypi.org> (or register), and switch on two-factor authentication,
   which PyPI requires.
2. **A pending publisher.** At <https://pypi.org/manage/account/publishing/>, under "Add a new pending
   publisher", choose GitHub and enter:
   - PyPI project name: `grownet`
   - Owner: `crossfeed-bio`
   - Repository name: `crossfeed` (or the new name, if the repository is renamed first)
   - Workflow name: `release.yml`
   - Environment name: `pypi`

   The first release then creates the project on PyPI under that account.
3. **A protected environment on GitHub.** In the repository's Settings, Environments, create `pypi`. Under
   "Deployment protection rules", add the maintainers as required reviewers, so publishing waits for a
   person's approval, and under "Deployment branches and tags" allow only tags matching `v*`.

## Each release

1. **A release pull request** that:
   - sets the version in `pyproject.toml` and in `src/crossfeed/__init__.py` (`__version__`);
   - turns `## [x.y.z] (unreleased)` in `CHANGELOG.md` into `## [x.y.z] - YYYY-MM-DD`, and starts a new
     unreleased section above it if work continues.
   `python packaging/check_release.py vX.Y.Z` must say the tag is ready.
2. **Merge it, then tag `main`:**

   ```bash
   git switch main && git pull
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

3. **Watch the workflow** (Actions, "release"). It checks the tag, builds and tests the wheel on Linux,
   Windows and macOS, builds and starts the Windows program, then waits for approval of the `pypi`
   environment. Approve it; it publishes to PyPI and creates the GitHub release, with the notes taken from
   the changelog and the wheel, the source archive and `grownet-vX.Y.Z-windows.zip` attached.
4. **Check as a user would:** `uv tool install grownet` then `grownet gui` on a clean machine, and the zip on
   a Windows machine. A version on PyPI cannot be replaced: a mistake is fixed with a new version.

## After the first release: signing the Windows program

The program is unsigned, so Windows warns on first start (the zip's README and the README explain it
beforehand). The route agreed on #26 and #63:

1. **The SignPath Foundation** signs open-source projects free of charge and requires an existing release
   in the form to be signed, which the first release provides. Apply at <https://signpath.org>. Signing
   lets Windows build up reputation across releases (an unsigned program starts from zero every time),
   should let it pass Smart App Control on Windows 11, and reduces antivirus false alarms. The publisher shown to
   a user is then the SignPath Foundation. The workflow gains a signing step before the zip is made.
2. **The Microsoft Store** (free, MSIX packaging) removes the warning entirely; worth it once the method has
   settled.
3. A commercial certificate is never bought: it would not remove the warning.
