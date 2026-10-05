# Releasing

Written by Claude (Karoline's agent) for the maintainers. How a version of the tool reaches its users: on
PyPI (`uv tool install grownet`, `pipx install grownet`) and as a self-contained Windows program attached to
the GitHub release. The `uvx --from git+...` route in the README needs no release; it always runs `main`.

Everything is automated by `.github/workflows/release.yml`, which runs when a version tag is pushed. The CI
jobs `package` and `windows-app` build and start the same artifacts on every push, so a release only
repeats what CI has already shown to work.

## Order for the first release (0.1.0)

1. #79 is reviewed and merged (done).
2. The rename (#71): the package, the module and the command are `grownet` (done, 2026-09-28, with no
   `crossfeed` alias, since nothing had been released). The repository name and the schema id are Craig's
   call and are unchanged.
3. The one-time setup below.
4. The release pull request, then the tag (below). For 0.1.0 it also renames the changelog's unreleased
   `[0.0.2]` section to `[0.1.0]` (0.0.2 was never published) and replaces the changelog's opening
   sentence about staying in the 0.0.x range.

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

   The first release then creates the project on PyPI under that account, its first owner.
3. **A second owner.** Right after the first release, the first owner opens the project on PyPI (Manage
   project, Collaborators) and invites the other maintainer's PyPI username with the role Owner; they
   accept from their own account, which needs two-factor authentication too. Karoline and Craig are both
   owners, in either order (Karoline, 2026-09-28: "I don't care wether I am first or 2nd"), so the project
   never depends on one account. Releases do not depend on either: they come from the workflow.
4. **A protected environment on GitHub.** In the repository's Settings, Environments, create `pypi`. Under
   "Deployment protection rules", add the maintainers as required reviewers, so publishing waits for a
   person's approval, and under "Deployment branches and tags" allow only tags matching `v*`.

## Each release

1. **A release pull request** that:
   - sets the version in `pyproject.toml` and in `src/grownet/__init__.py` (`__version__`);
   - turns `## [x.y.z] (unreleased)` in `CHANGELOG.md` into `## [x.y.z] (YYYY-MM-DD)`, and starts a new
     unreleased section above it if work continues.
   - bumps `Version:` in `r/DESCRIPTION` when anything in `r/` changed, since the R package is installed
     from GitHub and its version is the only signal an installed copy is out of date.
   `python packaging/check_release.py vX.Y.Z` must say the tag is ready, and `make check` must pass:
   among other things it refuses texts that describe work in progress rather than the released state (an
   install line pointing at one of our branches, for example).
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
4. **Refresh the daily All network** (Actions, "all-network", Run workflow). The page and `derive --all`
   read the published network only when it is less than a day old and speaks the current format, so until a
   run on the new code replaces it, All derives live instead. One click, and it matters most after a
   release that changes the format id.
5. **Check as a user would:** `uv tool install grownet` then `grownet gui` on a clean machine, and the zip on
   a Windows machine. A version on PyPI cannot be replaced: a mistake is fixed with a new version.

## After the first release: signing the Windows program

The program is unsigned, so Windows warns on first start (the zip's README and the README explain it
beforehand). The route agreed on #26 and #63:

1. **The SignPath Foundation** signs open-source projects free of charge and requires an existing release
   in the form to be signed, which the first release provides. Apply at <https://signpath.org>. **Not yet
   (Karoline, 2026-09-29):** the application asks the project to show that it "is widely used or trusted"
   (media coverage, blog posts, download statistics, GitHub insights, community discussions), which a
   project released that day cannot; "If we don't have that by the next release, we should explain to
   users how to click through the warning instead". So each release's notes open with how to get past the
   warning (`packaging/check_release.py`), as the README and the zip's README.txt do. Also needed when
   applying: a public code signing policy page (the SignPath attribution line, the team by role, and a
   privacy statement saying what the program sends where), two-factor authentication for every role,
   and a product name and version in `grownet.exe`'s file metadata. Signing
   lets Windows build up reputation across releases (an unsigned program starts from zero every time),
   should let it pass Smart App Control on Windows 11, and reduces antivirus false alarms. The publisher shown to
   a user is then the SignPath Foundation. The workflow gains a signing step before the zip is made.
2. **The Microsoft Store** (free, MSIX packaging) removes the warning entirely; worth it once the method has
   settled.
3. A commercial certificate is never bought: it would not remove the warning.
