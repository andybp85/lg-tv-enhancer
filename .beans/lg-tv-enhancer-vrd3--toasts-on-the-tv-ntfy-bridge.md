---
# lg-tv-enhancer-vrd3
title: Toasts on the TV (ntfy bridge)
status: draft
type: feature
created_at: 2026-07-08T10:39:30Z
updated_at: 2026-07-08T10:39:30Z
---

Exploratory: pop webOS toast notifications on the TV via ssap system.notifications/createToast (bscpylgtv wraps it). Candidate source: the ntfy topic tv-dsp already publishes recovery events to — a small subscriber on the Pi mirrors messages as TV toasts while watching.

Open questions before this is buildable:
- Which events deserve screen space (recovery only? laundry/doorbell class of things?)
- Toast length/rate limits on webOS 4.x; behavior when TV is off (drop vs queue)
- Separate daemon vs a hook inside the eye comfort loop's connection handling (probably separate — different cadence and lifetime)
