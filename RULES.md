# Ore Monorepo — Working Rules

**Last updated:** 2026-05-16

This document is the canonical reference for how we work in this repository. It applies to humans and to Claude Code equally. If anything in here conflicts with `CLAUDE.md`, `RULES.md` wins — `CLAUDE.md` is a derived view of these rules tailored to the agent.

---

## 1. Repository Layout

```
ore/
├── ore-stt/         # Python — Parakeet speech-to-text service
├── ore-agent/       # Go — agent core, tool registry, gRPC server
├── ore-app/         # Swift — macOS desktop client (Phase 2)
├── proto/           # Shared .proto files, source of truth
├── docs/            # Cross-package documentation
├── scripts/         # Repo-wide tooling (lint-all, test-all, etc.)
├── .githooks/       # Shared git hooks
├── .github/         # GitHub workflows and templates
├── CLAUDE.md        # Claude Code instructions (root)
├── RULES.md         # This file
└── README.md
```

Each package owns its own build tooling, its own dependency manifest, and its own `ARCHITECTURE.md`. The root holds only what is truly shared: protos, docs, scripts, hooks, and the rules.

---

## 2. Branches

### 2.1 Long-lived branches

- **`main`** — production. Tags and releases cut from here. Direct commits are forbidden.
- **`dev`** — integration. All feature work merges here first. Direct commits are forbidden.

### 2.2 Working branches

All working branches are created **from `dev`** and merged back into `dev`. Never branch from `main`.

Naming pattern (strict):

```
<type>/<short-kebab-description>
```

Allowed types:

| Type       | Purpose                                            |
| ---------- | -------------------------------------------------- |
| `feat`     | New feature or capability.                         |
| `bugfix`   | Fixing broken behavior.                            |
| `chore`    | Repo hygiene, dep bumps, no behavior change.       |
| `docs`     | Documentation-only changes.                        |
| `refactor` | Internal restructure with no behavior change.      |
| `test`     | Adding or fixing tests; no production code change. |

Examples:

- `feat/parakeet-loader`
- `feat/grpc-submit-endpoint`
- `bugfix/empty-audio-validation`
- `bugfix/button-not-working`
- `chore/bump-grpcio`
- `docs/ore-stt-architecture`
- `refactor/tool-registry-scopes`
- `test/audio-decode-fixtures`

Rules:

- Description is **kebab-case**. No underscores, no camelCase, no spaces.
- Description is short but meaningful. `feat/auth` is fine. `feat/stuff` is not.
- One branch, one logical change. If you find yourself doing two unrelated things, branch again.
- Branches are scoped to the work, not to the package. A change that touches both `ore-stt` and `ore-agent` is still one branch. Scope shows up in the commit messages and PR title, not the branch name.

### 2.3 Sync discipline

Before starting any work, and before opening a PR:

```bash
git checkout dev
git pull origin dev
git checkout <your-branch>
git rebase dev
```

**Always rebase on `dev` before opening a PR.** This keeps history linear and PR diffs honest. Merge commits from `dev` into your feature branch are noise; rebase them out.

If a rebase has more than ~5 conflicts, that's a signal the branch has been alive too long — split it.

---

## 3. Commits

### 3.1 Commit message format

We follow [Conventional Commits](https://www.conventionalcommits.org/) lightly. The format is:

```
<type>(<scope>): <subject>

<optional body>

<optional footer>
```

- `<type>` matches the branch type set (`feat`, `bugfix`, `chore`, `docs`, `refactor`, `test`).
- `<scope>` is the affected package: `stt`, `agent`, `app`, `proto`, `repo`. Omit if the change is genuinely cross-cutting.
- `<subject>` is lower-case, no trailing period, imperative mood ("add", not "added" or "adds"), 72 chars max.

Examples:

```
feat(stt): add parakeet model loader with warmup
bugfix(agent): validate audio bytes before STT call
chore(repo): bump golangci-lint to v1.59
docs(stt): document VAD trim opt-in flag
refactor(agent): split tool registry into scopes module
test(stt): add fixtures for silence and noisy audio
```

The body is optional but encouraged for anything non-obvious. Wrap at 72 chars.

### 3.2 Commit hygiene

- **Small, focused commits.** A reviewer should be able to read each commit in isolation and understand it.
- **No "WIP" commits in the final PR.** Squash or rebase before opening.
- **No "fix typo" / "fix CI" trail.** Squash these into the parent commit before review.
- **No commits that break the build.** Each commit on the branch should leave the tree green if checked out in isolation. In practice this means: if you have to break the build temporarily, squash before opening the PR.

### 3.3 Signed commits

Not required for v1, but encouraged. If you sign, sign consistently — don't mix signed and unsigned commits on the same branch.

---

## 4. Pull Requests

### 4.1 PR title

The PR title follows the same Conventional Commits format as commits:

```
<type>(<scope>): <subject>
```

Examples:

```
feat(stt): parakeet model loader with eager warmup
bugfix(agent): reject empty audio in Submit handler
chore(repo): add pre-push hook for branch name validation
```

The PR title is what lands on `dev` when the PR is squash-merged. It is the commit message that will live forever in history. Treat it accordingly.

### 4.2 PR target

All PRs target **`dev`**. PRs targeting `main` are only opened during release cuts and are merge-commits from `dev` (not squash).

### 4.3 PR description

Every PR uses the template at `.github/pull_request_template.md`. The template asks for:

- **What** — one paragraph on what changed.
- **Why** — link to the milestone, spec section, issue, or rationale.
- **How** — anything non-obvious about the approach.
- **Verification** — how the author tested it. Commands, fixtures, screenshots.
- **Risk** — what could go wrong; what's the blast radius.

PRs without a description are not ready for review.

### 4.4 Size

- **Small PRs are reviewed faster and merged faster.** Aim for < 400 lines changed.
- **A PR with > 800 lines changed should be split** unless there's a clear reason (e.g., a single large generated file).
- Splitting a PR after the fact is annoying. Splitting _before_ you start is free. Plan the split before writing code.

### 4.5 Reviews

- **Every PR requires at least one approving review** before merge.
- Solo work without a reviewer: self-review the PR in the GitHub UI as if it were someone else's. Walk every file, every diff. Surprisingly effective.
- Reviewers do not block on style nits the linter would catch. If it's a lint issue, fix the linter, not the PR.

### 4.6 Merge strategy

- **Squash and merge** is the default for feature branches → `dev`.
- **Merge commit** is used for `dev` → `main` release merges so the dev history is preserved.
- **Rebase and merge** is not used — squash gives us the same linear history with cleaner commit messages.

After merge, **delete the branch**. Stale branches are clutter.

---

## 5. Releases

Releases are cut from `dev` to `main`.

1. On `dev`: tag the merge commit as `v<major>.<minor>.<patch>` following semver.
2. Open a PR from `dev` to `main` with title `release: v<major>.<minor>.<patch>`.
3. Merge as a merge commit (not squash) so dev history is preserved in main.
4. Cut the GitHub Release from the tag, with changelog auto-generated from PR titles since the last release.

Per-package versions are independent. `ore-stt@0.3.0` and `ore-agent@0.5.1` can coexist. The repo-level tag is the snapshot of what was released together.

---

## 6. Cross-Package Discipline

The monorepo gives us atomic changes across packages. Use it.

- **Breaking change in `proto/`?** Update `ore-stt` and `ore-agent` in the same PR. Never merge a proto change that leaves one side broken.
- **Spec change in `docs/ore-spec.md`?** If the spec change implies a code change, do them together or open a follow-up PR immediately. A spec without corresponding code is a lie.
- **Shared utilities** don't get hoisted to a top-level package prematurely. Duplicate first, refactor when the third copy appears. Premature shared packages are worse than duplication.
- **Don't reach across packages.** `ore-agent` does not import from `ore-stt`'s source. They communicate via `proto/` and gRPC, period. The only thing they share is the protobuf definition.

---

## 7. Working with Claude Code

Claude Code reads `CLAUDE.md` and the rules here. The expectations:

- **Claude follows the branch and commit naming rules.** Always.
- **Claude never pushes to `dev` or `main`.** Always works on a `<type>/<description>` branch.
- **Claude never force-pushes to a shared branch.** Force-push is fine on your own working branch before review.
- **Claude rebases on `dev` before opening a PR.** Same as humans.
- **Claude proposes a branch name before starting work** if the user hasn't named one. The user can accept or override.
- **Claude does not merge its own PRs.** A human reviews.

See `CLAUDE.md` for the longer Claude-specific guidance.

---

## 8. Quick Reference

```bash
# Start new work
git checkout dev
git pull
git checkout -b feat/my-new-thing

# Keep up to date during work
git fetch
git rebase origin/dev

# Commit
git add -p              # stage hunks intentionally, not files wholesale
git commit -m "feat(stt): add parakeet loader"

# Open PR
git push -u origin feat/my-new-thing
# Then open PR in GitHub UI with title:
#   feat(stt): add parakeet model loader with eager warmup
# Targeting: dev
```

```
Branch:  <type>/<short-kebab>
Commit:  <type>(<scope>): <subject>
PR:      <type>(<scope>): <subject>
Target:  dev
Merge:   squash
```

---

## 9. Enforcement

- **`.githooks/pre-push`** — blocks direct pushes to `dev`/`main` and validates branch names locally.
- **`.github/workflows/pr-title.yml`** — validates PR title format in CI. Hard gate.
- **`.github/workflows/branch-name.yml`** — validates branch name format in CI. Hard gate.
- **Branch protection on `dev` and `main`** — configured in GitHub: no direct push, required PR review, required CI passing.

Hooks are opt-in locally (install via `scripts/setup-hooks.sh`). CI checks are not optional.
