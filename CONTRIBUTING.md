# Contributing

## Commit messages

Compass uses [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):

```
<type>(<optional scope>): <description>
```

Allowed types: `build`, `chore`, `ci`, `docs`, `feat`, `fix`, `perf`, `refactor`,
`revert`, `style`, `test`. Add `!` before the colon for a breaking change.

```
feat(api): add readiness endpoint
fix(db): use timezone-aware timestamps
docs(adr): record the monorepo decision
```

The format is enforced twice: locally by a `commit-msg` hook
(`conventional-pre-commit`) and in CI for every commit in a pull request.

## Before you push

```bash
make install   # dependencies + git hooks
make check     # lint, type-check, tests
```

`make install` registers both the `pre-commit` and `commit-msg` hook types, so
formatting, linting and type-checking run on staged changes automatically.

## Branching

Work on a branch, keep commits focused, and open a pull request. CI must be green:
lint/format/types, tests, commit message format, and the Docker build.

## Architecture changes

Decisions that shape the system are recorded as ADRs in `docs/adr/`. If a change
introduces or reverses such a decision, add or supersede an ADR in the same pull
request. Speculative ideas belong in `docs/roadmap.md`, not in an ADR.
