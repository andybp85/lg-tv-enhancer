---
# lg-tv-enhancer-cll7
title: Re-derive the lux bright edge from a full-cycle log, and document the sensor's quantization
status: completed
type: task
priority: normal
created_at: 2026-07-31T14:52:00Z
updated_at: 2026-07-31T14:53:44Z
---

The bright edge was raised 3.0 -> 7.0 on 2026-07-30 against a single 8.3 lux lamp sample. A 26h log was left running to verify the headroom.

Result: lamps never dropped below 7.0, but the margin was an illusion. The BH1750 in H-res reports raw/1.2, so only multiples of 0.833 lux exist. Lamps pin to the 7.50 step and the next step down is 6.67 — under the old edge. The room was one sensor count from silently falling out of Bright.

- [x] Read the 26h CSV and answer whether lamps ever read below 7.0
- [x] Lower the bright edge to 4.6 (midpoint of the 4.17/5.00 steps, 3 steps of margin)
- [x] Add LGTV_LUX_DARK_BELOW to the config explicitly — it was riding the code default, so only the bright side had ever been calibrated
- [x] Document the lattice constraint in the README calibration section

## Summary of Changes

Answered from a 26h BH1750 log (9366 samples, no gaps).

**The question:** does the room ever read below the 7.0 bright edge with lamps on? **No** — night-lit readings were 7.5 (min, median and mode) with a max of 8.3.

**The real finding:** the margin was an illusion. H-res reports `raw/1.2`, so only multiples of 0.833 lux exist. Lamps pin to step 9 (7.50) and the next step down is step 8 (6.67), which is *under* 7.0 — the room sat one sensor count from silently dropping out of Bright. The "1.3 lux of headroom" in the original note came from comparing against a single 8.3 sample.

**Changes:**

- Bright edge 7.0 -> 4.6 (midpoint of steps 4.17/5.00, three steps of margin).
- `LGTV_LUX_DARK_BELOW` written explicitly, pinned at its former implicit 1.0. Nothing dwells between 0.0 and 1.7 in this room, so it has no behavioral lever — the point is that half the deadband was invisible in config and only the bright side had ever been calibrated.
- README calibration section and `systemd/lg-tv-enhancer.env.example` document the lattice constraint and the set-both-edges rule.

**Correction worth recording:** an early pass counted dusk "flapping" by bucketing the CSV into dark/mid/bright and counting transitions, reporting 28 band changes. That model is wrong — `_target` returns the current band inside the deadband, so mid<->bright churn is a no-op. Simulating the real `select_band` gives **3 preset changes in 26h, identical at 7.0 and 4.6**, and identical at hold 5s vs 30s. Lowering the edge bought lamp margin and nothing else; it slightly *narrowed* the deadband (6.0 -> 3.6 lux).
