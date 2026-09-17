# Instructions for coding agents

This file is the single source of project instructions for any coding agent (Claude Code, Codex, Copilot,
and others) working on crossfeed. Humans are welcome to read it too. `CLAUDE.md` only imports this file,
so edit instructions here and nowhere else.

## Start of every session

1. Read this file, then [docs/agents/NOTES.md](docs/agents/NOTES.md) (the shared agent memory).
2. Read [README.md](README.md) and [CONTRIBUTING.md](CONTRIBUTING.md) if you have not in this session.
3. Look at the open GitHub Issues (`gh issue list`) and take the role the person you work for asks for
   (below). If they name no role, ask.

## Workflow: features, tasks, roles

Everything is tracked in GitHub Issues, never in a file in the repository: anyone can open and comment on
issues without write access, and several agents can work at once without merge conflicts.

- A **feature** is a higher-level goal written by a human, as an issue from the Feature form (label
  `feature`). It states the goal, the context, and the acceptance criteria.
- A **task** is a concrete, independently mergeable job, as a sub-issue of its feature (Task form, label
  `task`). One task, one pull request.

### Claiming

Before doing anything to an issue, claim it: comment "Claiming this (agent of <GitHub account>)", and
assign it too if you have triage access (`gh issue edit N --add-assignee @me`). Do not take an issue that
is already claimed unless its owner agrees. If you stop without finishing, comment that you released it.

### Role: mayor (breaks a feature into tasks)

1. Pick an open `feature` issue that has no tasks yet and claim it ("Planning this").
2. Read the feature, the code it touches, and docs/agents/NOTES.md. Ask questions on the feature issue if
   the goal or the acceptance criteria are unclear, and stop until a human answers.
3. Create the tasks as sub-issues: `gh issue create --parent N --template task.yml` (or pass `--title`
   and `--body` following the Task form). Each task is small, testable, and names its own acceptance
   check. Note dependencies between tasks ("after #M").
4. Anything that needs a human or scientific choice becomes a sub-issue labeled `needs-decision`, not a
   task. Every change to the derivation method is such a choice (see [docs/METHOD_NOTES.md](docs/METHOD_NOTES.md)).
5. Comment on the feature with the plan: the list of tasks, their order, and any open decisions. The
   mayor does not set priorities between features; humans do.

### Role: worker (implements a task)

1. Pick an open `task` with no open dependencies and no claim, and claim it.
2. Implement it following "How to make a change" below. The pull request says `Closes #N`, so the task
   closes on merge and the feature's sub-issue progress updates.
3. Work you discover but do not do becomes a new sub-issue of the same feature, not a note buried in a
   pull request.

### Role: verifier (checks a feature is done)

1. When every task under a feature is closed, check out `main`, run `make check`, and test each
   acceptance criterion of the feature (commands and their output).
2. Comment on the feature with the evidence, one line per criterion: met or not met. Open new tasks for
   anything not met.
3. A human closes the feature.

### Labels

`feature`, `task`, `needs-decision` (blocked on a human choice; do not implement), `method` (touches the
derivation method). Labels are created by a maintainer; if one is missing, say so in your comment.

## How to make a change

1. Branch from `main` (`git switch -c short-topic-name`). Never push to `main` directly. Without write
   access, push the branch to your fork and open the pull request from there.
2. Keep the change small and focused, matching the surrounding code.
3. Run `make check` (lint, guardrail gate, tests). All three must pass before you open a pull request.
4. Add a line to [CHANGELOG.md](CHANGELOG.md) for any user-facing change.
5. Update [docs/agents/NOTES.md](docs/agents/NOTES.md) in the same pull request with what the next agent
   needs to know (see the rules in that file).
6. Open the pull request with `gh pr create`, linking the issue. A human reviews and merges.

## Hard rules

- **No real data in git.** Only the synthetic fixtures under `tests/fixtures/` belong in the repository.
  Nothing pulled from mGrowthDB, nothing shared by a collaborator, no cached API responses. See
  [docs/DATA_GOVERNANCE.md](docs/DATA_GOVERNANCE.md).
- **Unpublished collaborator data** is used only for the agreed analysis, never written into issues,
  pull requests, or the notes file.
- **The derivation method is a scientific decision** owned by the collaboration. Do not change
  `BaselineDeriver` or implement a new method without an issue where a human has settled the choice. The
  menu of choices is in [docs/METHOD_NOTES.md](docs/METHOD_NOTES.md).
- **The neutral format is a contract.** If `src/crossfeed/model.py` changes, regenerate the schema
  (`python -m crossfeed schema --out schema/interaction_network.schema.json`) and keep it backward
  compatible where possible.
- **No runtime dependencies.** Code under `src/` imports only the standard library and crossfeed.
- **Nothing public bearing a collaborator's name or affiliation** without their sign-off.
- **Security problems are reported privately** (see [SECURITY.md](SECURITY.md)), never in a public issue,
  pull request, or the notes file.
- **This repository is public.** Everything you commit, and every issue or comment you write, is public.

## House style (enforced by `checks/gate.py`)

These trip agents most often, especially in notes and pull request text copied into docs:

- No em dash or en dash, and no spaced hyphen used as a dash. Use a comma, colon, parentheses, or "to".
- US spelling (behavior, analyze, modeling, license).
- No hedging caveat words (the gate keeps the list in `checks/gate.py`). Say it plainly.
- No absolute local paths (for example a home directory path). Use repository-relative paths.
- No secrets or tokens anywhere.

## Setup

```
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
make check
```

The GitHub CLI (`gh`) must be installed and authenticated for issue and pull request work.

## Project instructions from the humans

Standing instructions that a collaborator gives an agent belong here, so every agent inherits them. Add
them as a dated bullet with who gave them. Keep one-off requests out.

- 2026-09-17 (Karoline's Claude agent): This repository is an experimental project for agent-based
  programming. Humans describe features as issues; agents break them into tasks (mayor), implement them
  (worker), and check them (verifier). Shared state lives in `docs/agents/NOTES.md`, project instructions
  in this file.
