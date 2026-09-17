# Agent notes (shared memory)

This is the handoff file between agent sessions. Read it at the start of a session and update it in the
same pull request as your change.

Rules for this file:

- Record what is not obvious from the code, the git history, or the issues: decisions and their reasons,
  dead ends, quirks of external systems, open questions.
- Edit in place. Replace stale entries instead of appending contradictions. This is not a session log;
  the history lives in commits and pull requests.
- Date each entry (YYYY-MM-DD) and link the issue or pull request when there is one.
- Tasks do not go here. They are GitHub Issues.
- The repository is public and the house style gate applies (see [AGENTS.md](../../AGENTS.md)).

## Current state

- 2026-09-17: v0.0.2 is unreleased on `main`. The pipeline runs end to end on live mGrowthDB data with
  the provisional `BaselineDeriver`. CLI: `derive`, `validate`, `schema`; outputs JSON and GraphML.

## Decisions

- 2026-09-14: Attribution is at the edge level (each edge cites its supporting studies) rather than
  bundling licenses. See [docs/DATA_GOVERNANCE.md](../DATA_GOVERNANCE.md).
- 2026-09-17: Agent workflow set up: instructions in `AGENTS.md`, shared memory in this file. Features
  (human) and tasks (sub-issues) live in GitHub Issues, not in a master file, because contributors
  without write access can still open and comment on issues, and parallel agents do not conflict. Roles:
  mayor, worker, verifier. The repository is an agreed experiment in agent-based programming.
- 2026-09-17: An account with read-only access cannot attach sub-issues: `gh issue create --parent N`
  creates the issue but fails on `addSubIssue`. Without triage or write access, the mayor lists the
  tasks in a comment on the feature and writes "Feature: #N" in each task (as on #3).
- 2026-09-17: Without write access, dependent tasks go out as stacked pull requests from a fork, each
  based on `main`; the description says to merge in order and review only the last commit.

- 2026-09-17: `main` requires one approving review, and GitHub never lets a pull request's author
  approve it. A pull request opened by an agent under a person's account therefore needs a review from
  someone else (another collaborator or their agent).
- 2026-09-17: Collaborators with write access push branches to this repository, not a fork, so CI
  runs without maintainer approval and later branches can stack on earlier ones.

## Open questions (need a human)

- Which derivation method choices (rows 1 to 4 in [docs/METHOD_NOTES.md](../METHOD_NOTES.md)) the first
  real FP/BH network should fix, and whether it carries a significance call.
- Where each mGrowthDB study's license is published; the study endpoint does not expose it, so
  `study_license` is marked unresolved.

## Gotchas

- mGrowthDB serves growth curves, not interactions; interactions are derived.
- Study SMGDB00000008 (13 to 14 member deletion consortia) yields an empty network under the pairwise
  baseline. That is expected, not a bug.
- In the FP/BH study, monoculture and co-culture growth use different measurement techniques; edges carry
  a technique-mismatch flag, so direction is dependable and magnitude is provisional.
- The gate scans every tracked file, including this one: no dashes as punctuation, US spelling, no
  absolute local paths.
