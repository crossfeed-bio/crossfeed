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
   - moves the entries under `## [Unreleased]` in `CHANGELOG.md` into a new `## [x.y.z] (YYYY-MM-DD)`
     section below it, leaving `## [Unreleased]` empty; the release check refuses an empty version section;
   - adds the version and the same date to `RELEASES` in `src/grownet/help.py`, the "what changed" list
     the help page shows; the release check refuses a date there that differs from the changelog's;
   - sets `version:` and `date-released:` in `CITATION.cff` to the same version and the same date, and
     that date is **the day the tag is cut**: the release check refuses a date more than a day old, since
     a date prepared earlier is otherwise invisible to every other check. The
     check refuses a mismatch, and it is the file the citation widget and every generated BibTeX entry
     read: 0.3.0 was prepared with 0.2.0's date still in it, which nothing read at the time.
   - sets `Version:` in `r/DESCRIPTION` to the same version, on every release: the R package is installed
     from GitHub, its version is the only signal an installed copy is out of date, and the release check
     requires it.
   `python packaging/check_release.py vX.Y.Z` must say the tag is ready, and `make check` must pass:
   among other things it refuses texts that describe work in progress rather than the released state (an
   install line pointing at one of our branches, for example).
2. **Merge it, then tag `main`:**

   ```bash
   git switch main && git pull
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

3. **Watch the workflow** (Actions, "release"). It checks the tag against the version and the changelog
   and runs the linter, the guardrail gate and the whole suite before anything is published, then builds
   and tests the wheel on Linux, Windows and macOS, builds and starts the Windows program, and waits for
   approval of the `pypi` environment. Until 2026-10-07 the first of those was the only check in this
   workflow, so a tag whose suite was red could reach PyPI with nothing but that approval in the way. Approve it; it publishes to PyPI and creates the GitHub release, with the notes taken from
   the changelog and the wheel, the source archive and `grownet-vX.Y.Z-windows.zip` attached.
4. **Refresh the daily All network** (Actions, "all-network", Run workflow). The page and `derive --all`
   read the published network only when it is less than 36 hours old and speaks the current format, so until a
   run on the new code replaces it, All derives live instead. One click, and it matters most after a
   release that changes the format id. A run that keeps less than half the arcs of the artifact it would
   replace is refused (#236); when the drop is meant, as after a release that changes the derivation, tick
   `allow_drop` in the Run workflow form. Each run rewrites the release description from what it
   produced, so the description is never edited by hand. The daily run builds `main`, not a release, so
   the floor meets a change to the derivation the morning after it MERGES: that is when to run it by hand
   with `allow_drop`, if the drop is meant.
5. **Check as a user would:** `uv tool install grownet` then `grownet gui` on a clean machine, and the zip on
   a Windows machine. A version on PyPI cannot be replaced: a mistake is fixed with a new version.

## If the live check fails

After each daily publish, `packaging/live_check.py` checks the file just derived from the live mGrowthDB,
and one study derived in gLV mode, for properties the tool promises rather than numbers: every arc carries
the fields its evidence and outcome promise, `strength` is `log2(metric_with / metric_without)` under the
comparison and `coefficient` is `(metric_with - metric_without) / partner_abundance` under the integrated
form, the network validates with no undeclared key, and nothing is empty (#237). It is the one check that
reads a real mGrowthDB response. A violation opens an issue labeled `live-check-failed`, whose run log
names every arc; the artifact was published anyway, because every copy derives the same thing live, so
the fix is in the code. Run it by hand with `python packaging/live_check.py DIR`, where `DIR` holds the
files the workflow writes.

## If the daily All artifact is broken

The `all-network` workflow publishes the All network as assets of the `all-network` release, from
`main`, once a day: `all_result.<format>.json` (today `all_result.v4.json`), named by the format id a copy
reads, and `all_result.json`, the same network in `/v3` for installed 0.3.x and 0.4.x copies (#289). A
copy of this version reads its file while it is less than 36 hours old; 0.3.x and 0.4.x read theirs while
it is less than a day old. If a bad artifact goes out, **pause the workflow, then delete every result file**:

```bash
gh workflow disable all-network
for status in in_progress queued pending waiting; do
  gh run list --workflow all-network --status "$status" --json databaseId -q '.[].databaseId' | xargs -r -n1 gh run cancel
done
gh release view all-network --json assets -q '.assets[].name' | grep '^all_result' | xargs -r -I{} gh release delete-asset all-network {} --yes
```

Pausing comes first because the next scheduled run would otherwise rebuild the same file from the same
`main` and publish it again, and disabling does not stop a run already going or one queued behind it, hence the cancel. Every
`all_result*.json` goes, one per format a copy may read, not only the two there today. Turn it back on with `gh workflow enable all-network` once the fix has merged;
with every result file gone, that first run compares itself with `all_network.json` for the floor.

`published.fetch` then gets nothing, returns `None`, and every copy derives live, which is the designed
fallback and is what the All button does when GitHub is unreachable. `all_network.json` and
`all_report.txt` stay: no copy of grownet reads them, and the next run's floor compares itself with
`all_network.json`. Verify that every result file is gone for every reader, not only for the version
installed where you check:

```bash
gh release view all-network --json assets -q '.assets[].name' | grep '^all_result'
```

It should print nothing.

This was found under pressure on 2026-10-07, when #121's arc fields went out under an unchanged format id
and the All button raised for every installed 0.2.0. It is written down because it is not obvious from
the workflow, and because the obvious alternative is not available: **do not plan to beat the next
scheduled run.** The cron says `17 3 * * *` and has never fired near it. Five consecutive days ran at
10:19, 10:22, 10:31, 09:51 and 09:12 UTC, six to seven hours late and varying by over an hour, because
GitHub treats schedules as best effort. Anyone racing the clock cannot tell whether they have twelve
hours or none (Craig's agent, correcting his own estimate on #154).

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
