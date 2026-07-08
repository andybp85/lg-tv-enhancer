---
# lg-tv-enhancer-4cth
title: Scrub usernames/addresses for public release
status: completed
type: task
priority: normal
created_at: 2026-07-08T10:54:14Z
updated_at: 2026-07-08T10:58:40Z
---

Make the repo publishable: parameterize deploy identity (PI_USER/PI_HOST) via git-ignored .env with a committed .env.example; genericize systemd unit to pi defaults; scrub the personal Pi login from tree AND history (git-filter-repo replace-text; repo has no remote so rewrite is safe); install pre-commit PII guard.

## Summary of Changes
- .env.example (PI_USER/PI_HOST) + .env gitignored; README deploy commands read them.
- systemd unit genericized to pi defaults with an adjust-note.
- Bean bodies scrubbed; history rewritten with git-filter-repo replace-text (all hashes changed; in-message hash refs auto-updated; pre-scrub backup bundle at ../lg-tv-enhancer-pre-scrub.bundle).
- pii-commit-guard pre-commit hook installed in .git/hooks (untracked by design): blocks the login name, gmail/handle, home paths, all IPv4s and pairing-key assignments, with an allowlist for documented placeholders (/home/pi, $PI_USER, 192.168.1.50, 10.0.0.2 test fixture, loopback). Verified: probe blocked, clean tree passes.
- Note: hook lives outside the tree — reinstall via bash ~/.claude/skills/pii-commit-guard/install.sh in any fresh clone.
