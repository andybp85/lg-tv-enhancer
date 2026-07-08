---
# lg-tv-enhancer-p5f5
title: Verify DoVi black level on the C9 (Netflix Test Patterns)
status: todo
type: task
created_at: 2026-07-08T10:51:12Z
updated_at: 2026-07-08T10:51:12Z
---

Check whether the C9's Dolby Vision pipeline raises near-blacks (the known LG DoVi bug) using an independent test — no hardware needed.

## Test procedure
1. **PLUGE test (definitive):** open Netflix, search "Test Patterns" (Florian Friedrich's series, made for this). Play a Dolby Vision episode with the black-clipping / PLUGE pattern. Bars at-and-below reference black should be completely invisible. Faintly glowing below-black bars = raised blacks.
2. **Letterbox sanity check:** fully dark room (no standby LEDs), eyes adapted ~30s, pause a 2.39:1 DV title on a dark scene. Letterbox bars should be indistinguishable from the powered-off bezel — picture should appear to float.

Not the same bug: brief near-black flicker/noise in dark gradients (different C9 OLED artifact); films that bake letterboxing into the graded image can raise bars legitimately.

## Outcome
- Bars invisible → no action; close this bean. The mitigation (pushing a modified Dolby Vision config to the panel, guide below) is not worth the risk for an invisible gain.
- Bars visible → open a follow-up bean referencing https://github.com/chros73/bscpylgtv/tree/master/docs/guides/mitigating_dovi_raised_black

## Todo
- [ ] Run the Netflix Test Patterns DV PLUGE check
- [ ] Dark-room letterbox comparison
- [ ] Record result here; follow-up bean only if blacks are raised
