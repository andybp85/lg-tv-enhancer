---
# lg-tv-enhancer-4cth
title: Scrub usernames/addresses for public release
status: in-progress
type: task
priority: normal
created_at: 2026-07-08T10:54:14Z
updated_at: 2026-07-08T10:55:06Z
---

Make the repo publishable: parameterize deploy identity (PI_USER/PI_HOST) via git-ignored .env with a committed .env.example; genericize systemd unit to pi defaults; scrub the personal Pi login from tree AND history (git-filter-repo replace-text; repo has no remote so rewrite is safe); install pre-commit PII guard.
