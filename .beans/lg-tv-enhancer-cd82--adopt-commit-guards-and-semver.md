---
# lg-tv-enhancer-cd82
title: Adopt commit guards and SemVer
status: completed
type: task
created_at: 2026-07-31T17:30:29Z
updated_at: 2026-07-31T17:30:29Z
---

Installed the pre-commit guards and adopted versioning, per the SessionStart prompts.

- [x] Install secrets-commit-guard
- [x] Install update-docs-before-commit guard
- [x] Adopt SemVer at 0.1.0 and scaffold a Keep a Changelog CHANGELOG.md

## Summary of Changes

Guards chain via a dispatcher at `.git/hooks/pre-commit`, running `00-original` (the pre-existing PII guard, preserved by the installer) -> `10-secrets-guard` -> `20-docs-guard`. All three are untracked, so they need reinstalling per clone.

Versioning: no packaging manifest exists — the project is deployed by copying the tree to the Pi, not installed — so the version lives in `src/version.py` as `__version__`. Started at 0.1.0: single deployment, surface still moving.

Also declared the public surface in the README, without which no future bump is decidable. It is deployment-facing (env vars, unit names, tools/ CLI, operator-visible behavior), explicitly NOT the Python modules — nothing imports this as a library, so `src/` is internal and free to change in a patch.
