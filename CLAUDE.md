# CLAUDE.md — Ore Monorepo

This file tells Claude Code how to work in this repository. The canonical workflow rules live in [`RULES.md`](./RULES.md); this file adds Claude-specific guidance on top.

**If anything here contradicts `RULES.md`, `RULES.md` wins.** This file is a derived view, not an override.

---

## 1. The repository in one paragraph

Ore is a voice-activated personal agent for macOS. Three packages in this monorepo:

- **`ore-stt/`** — Python service wrapping NVIDIA Parakeet for speech-to-text. gRPC server.
- **`ore-agent/`** — Go service hosting the agent core, tool registry, and SQLite store. gRPC server.
- **`ore-app/`** — Swift macOS desktop app (Phase 2). Owns hotkey + mic + notifications. gRPC client.

The agent is the single front door. Audio enters via the agent's `Submit` gRPC, which forwards to `ore-stt`, runs the LLM loop, executes tools, and streams events back. Read [`docs/ore-spec.md`](./docs/ore-spec.md) for the full architecture.

---

## 2. Workflow rules Claude must follow

These mirror `RULES.md` §2-4. **Claude follows them without being reminded.**

### Branches

- Always create branches from `dev`. Never from `main`. Never push directly to either.
- Branch name: `<type>/<short-kebab-description>`. Types: `feat`, `bugfix`, `chore`, `docs`, `refactor`, `test`.
- One branch, one logical change. If scope expands, propose splitting before writing code.

### Commits

- Format: `<type>(<scope>): <subject>` — e.g. `feat(stt): add parakeet model loader`.
- Imperative mood, lower-case, no trailing period, 72 chars max for the subject line.
- Scopes: `stt`, `agent`, `app`, `proto`, `repo`. Omit for genuinely cross-cutting changes.
- Small, focused commits. No "WIP" commits in the final PR. Squash noise before opening.

### PRs

- Title follows the same `<type>(<scope>): <subject>` format as commits.
- Always target `dev`. Never `main` (release cuts are a human-driven exception).
- Use the template at `.github/pull_request_template.md`. Fill all sections.
- Aim for < 400 lines changed per PR. Propose splitting if a change will exceed ~800 lines.
- Claude does not merge its own PRs. A human reviews.

### Sync

- Before starting work: `git checkout dev && git pull`.
- Before opening a PR: rebase the branch on `dev`. Resolve conflicts on the branch, not via merge commit.

---

## 3. How Claude should propose and start work

When the user asks for a change, Claude does this in order:

1. **Restate the goal in one sentence.** Confirms understanding before any code.
2. **Identify which package(s) are affected.** `ore-stt`, `ore-agent`, `ore-app`, `proto`, or root.
3. **Propose a branch name** matching the naming rules. Wait for the user to accept or override.
4. **Check out `dev`, pull, and branch.** Only after the user confirms the name.
5. **Outline the plan briefly** before writing code if the change is non-trivial (more than one file or more than ~50 lines of new code). Skip the outline for genuinely small changes.

Example:

> User: "Add a healthz endpoint to the STT service."
>
> Claude: "Goal: add a `/healthz` HTTP endpoint to `ore-stt` returning 200 when the process is up. Affected package: `ore-stt`. Proposed branch: `feat/stt-healthz-endpoint`. Plan: add `src/ore_stt/http/admin.py` with a FastAPI app, mount it from `server.py`, add a unit test. OK to proceed?"

---

## 4. Per-package navigation

Each package has its own `CLAUDE.md` with stack-specific rules. Read it when working in that package:

- [`ore-stt/CLAUDE.md`](./ore-stt/CLAUDE.md) — Python, uv, ruff, mypy strict, structlog, gRPC + FastAPI.
- [`ore-agent/CLAUDE.md`](./ore-agent/CLAUDE.md) — Go 1.22+, gRPC, LangChainGo, SQLite, golangci-lint.
- [`ore-app/CLAUDE.md`](./ore-app/CLAUDE.md) — Swift, SwiftUI, AVAudioEngine, Phase 2.

Each package also has an `ARCHITECTURE.md` describing its design. **Read the relevant `ARCHITECTURE.md` before making non-trivial changes to a package.**

---

## 5. Things Claude does autonomously vs. asks first

### Autonomously fine

- Reading any file in the repo.
- Running lint, typecheck, test commands in any package (`make lint`, `make test`, etc.).
- Creating branches matching the naming rules.
- Writing code on a feature branch.
- Squashing or rebasing the current feature branch.
- Updating `ARCHITECTURE.md` to match code changes in the same PR.

### Asks first

- Changing `RULES.md` or any `CLAUDE.md`.
- Changing `.githooks/`, `.github/workflows/`, or branch protection assumptions.
- Adding a new top-level package or restructuring the monorepo.
- Bumping major versions of core dependencies (Go, Python, Swift toolchain, gRPC, NeMo).
- Changing any `proto/*.proto` file (always asks; proto changes are breaking changes by default).
- Force-pushing to a shared branch. **Never** force-pushes to `dev` or `main`.
- Merging a PR. Claude never self-merges.

### Refuses

- Direct commits to `dev` or `main`. The hook will block this; Claude does not try to work around the hook.
- Force-pushing to `dev` or `main`.
- Pushing branches whose name doesn't match the naming rules.
- Opening PRs without filling the description template.

---

## 6. Cross-package changes

Some changes touch multiple packages — most commonly a `proto/` change that requires updates in both `ore-stt` and `ore-agent`.

Rules:

- **Proto change + consumers go in the same PR.** Never merge a proto change that leaves one side broken.
- **Regenerate stubs in the same commit as the proto edit.** `ore-stt`'s Python stubs live in `ore-stt/src/ore_stt/grpc/generated/`. `ore-agent`'s Go stubs live in `ore-agent/internal/proto/`. The commit that edits `.proto` also commits regenerated stubs.
- **Update both packages' tests.** A proto change is a contract change; both sides need test coverage.
- **Scope in commit message:** use `proto` for the proto edit commit; subsequent commits use `stt` or `agent` as appropriate.

Example commit sequence on a single PR:

```
proto: add session_id field to SubmitRequest
feat(agent): thread session_id through Submit handler
feat(stt): no-op — regenerated stubs only
test(agent): cover session_id continuation
```

---

## 7. Testing expectations

Before opening a PR, Claude runs the affected package's test suite locally and confirms it passes.

| Package     | Fast test command           | Full test command       |
| ----------- | --------------------------- | ----------------------- |
| `ore-stt`   | `cd ore-stt && make test`   | `make test-e2e`         |
| `ore-agent` | `cd ore-agent && make test` | `make test-integration` |
| `ore-app`   | `cd ore-app && make test`   | (manual on macOS)       |

Repo-wide:

```bash
./scripts/lint-all.sh
./scripts/test-all.sh
```

If a test fails, **Claude does not open the PR.** Fix the failure first, or surface the failure to the user with the failing output and ask how to proceed.

---

## 8. Documentation discipline

- Code changes that affect public behavior update the relevant `ARCHITECTURE.md` in the same PR.
- New tools added to `ore-agent` update the built-in tools table in `ore-agent/ARCHITECTURE.md`.
- gRPC contract changes update `proto/` AND any `ARCHITECTURE.md` sections that describe the contract.
- The root `docs/ore-spec.md` is the high-level spec; only update it when the high-level design genuinely shifts. Day-to-day code changes do not edit the spec.

---

## 9. Common pitfalls Claude avoids

- **Importing across packages.** `ore-agent` does not import `ore-stt` source. They talk over gRPC. The only shared thing is `proto/`.
- **Storing audio.** `ore-stt` discards audio after transcription. No on-disk persistence of raw audio.
- **Wide capability grants.** New tools declare the narrowest `Capability` set that works. Adding `network` because "we might need it" is rejected on review.
- **Spec drift.** If code disagrees with `ARCHITECTURE.md`, fix one of them in the same PR. Don't leave them inconsistent.
- **Generated files in source review.** gRPC-generated code is in the repo (for build reproducibility) but isn't reviewed line-by-line. Don't manually edit it.

---

## 10. When in doubt

Read these, in order:

1. [`RULES.md`](./RULES.md) — workflow rules.
2. [`docs/ore-spec.md`](./docs/ore-spec.md) — overall system design.
3. The relevant package's `ARCHITECTURE.md`.
4. The relevant package's `CLAUDE.md`.

If still unclear, ask the user before writing code. Asking once costs five minutes; building the wrong thing costs an afternoon.
