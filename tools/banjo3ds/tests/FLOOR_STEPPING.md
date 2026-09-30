# M4.7B.5 — bounded floor following, not M4.7C movement integration

## Strategy comparison and decision

- A fixed empirical segment (for example 5 units) preserves individual queries,
  but costs five scans for a 25-unit update and does not explain its safety bound.
- A bound derived from the existing vertical window and normal threshold keeps
  the same query and is valid even when the next continuous triangle is steeper
  than the current one. Adapting to the **current** triangle alone is unsafe at
  such a boundary; using the global accepted normal limit needs no new data.
- Enlarging the vertical window changes which overlapping/stacked floors can be
  selected and which discontinuous height changes can be crossed. It is rejected.

Selected: equal-length horizontal segments, globally bounded by the original
normal/window contract. No new collision data, acceleration or player state.

For a unit plane normal with `|ny| >= n = .432`:

```
|gradient Y| = sqrt(nx^2+nz^2)/|ny| <= sqrt(1-n^2)/n = 2.08767038272
|deltaY| <= horizontalLength * 2.08767038272
horizontalLength <= 30*n/sqrt(1-n^2) = 14.37008459205
```

Round DOWN to a whole unit: **14**. This leaves about .7726 vertical units of
margin against the exact geometric bound. The constant is calculated from
`MOVEMENT_STEP` and `MOVEMENT_MIN_NORMAL_Y`, not fitted to the asset. Floating
coordinate/plane evaluation is still subject to the existing query's precision.

`N = max(1, ceil(horizontalDistance / 14))`. At 500 units/s and dt <= .05,
the maximum candidate length is 25 units: at most **two floor scans**. At the
current 150 units/s, candidate length <=7.5: exactly **one unchanged query**.
There are no per-frame allocations and no persistent stepping state.

## Transaction and selection semantics

`movementFollowFloor()` receives a previously confirmed start position and an
absolute X/Z endpoint. The caller remains responsible for confirming the start
(the current jump runtime already does this). It performs no extra start query
that could change the initial selected layer.

Each segment endpoint calls the original, unmodified `movementFloor()` using the
preceding successful height. Rejectmask, .432 normal test, 0x10000 two-sided
handling, inclusive +/-30 window and highest-valid-floor selection are unchanged.
Intermediate X/Z coordinates are interpolated from the original start; the last
query uses the exact caller endpoint, avoiding incremental drift.

If **any** query fails, the full frame candidate is rejected. The output height
is untouched and `movementUpdate()` commits no position or yaw. No partial
progress is kept. This preserves M4.2's atomic acceptance contract. A future
horizontal-velocity caller must separately record accepted displacement; this
helper never alters velocity.

The current viewer still runs at 150 units/s, with the same candidate arithmetic,
normalization, deadzone, camera and yaw calculation. It now calls the helper, but
its one query is bit-identical to the old query, including overlapping floors.
Airborne sweep/vertical physics and jump code are not changed.

## Scope of the geometric proof

The bound prevents loss of a **continuous accepted floor** solely because its
slope makes a long sample exceed the +/-30 window. It also applies to piecewise
continuous accepted planes along the path. It does not prove absence of holes
narrower than the sample spacing, or continuity across discontinuous layers.
This remains ordered point-floor sampling, not a continuous ground sweep.

Every intermediate sample must succeed; a supported final endpoint cannot rescue
an earlier failed sample. For overlapping floors the original highest-in-window
rule is history-dependent: adding query points can select different layers.
Partition invariance is asserted for the tested continuous floors, not universally
for arbitrary stacks of disconnected surfaces. Tests explicitly preserve this
per-query behavior rather than silently introducing a new surface-selection rule.

## Permanent independent reproduction and asset scan

`floor_step_reference.py` parses actual 14CF bytes independently of the production
collision exporter and pins its SHA256. It implements binary64 geometric queries
without importing production collision code. The host tests compare against the
actual C query at -O0/-O2; heights allow .001 units where float precision differs.

Record 1196 after deduplication:

- original vertices 412, 415, 413; flags 0x100, surface 0;
- vertices (-1937,200,-153), (-1860,-50,-338), (-2485,250,-660);
- normal Y .593683882379;
- start (-2094,133.333343506,-383.666656494), yaw 135 degrees;
- 150*.05 and 500/60 already pass the original query;
- 500*.05 fails the original query, but two ordered queries end at
  approximately **99.449371** and match multiple smaller straight updates.

The independent whole-14CF scan finds **1474** records passing flags/normal tests.
Maximum plane slope: record **2890**, normal Y .442098819183, flags 0x100,
vertices 819/816/827. Its 25-unit height-change bound is **50.7220507985**, and a
25-unit segment entirely inside that triangle reaches the bound:

```
start (3983.203899509, -192.361025399, 6528.551129399)
end   (3985.462767158, -141.638974601, 6553.448870601)
```

This is the geometric maximum over the eligible individual planes, not a claim
about spawn reachability or arbitrary disconnected floor-layer jumps. It is
analysis, not justification for increasing the Y window.

Reproduce the scan:

```
.venv/bin/python -B tools/banjo3ds/tests/floor_step_reference.py
```

Run regressions:

```
.venv/bin/python -B -m unittest discover -s tools/banjo3ds/tests -v
```

No horizontal goldens, gait rules, generated data, runtime speed, jump vertical
physics, swept landing, recovery or renderer behavior are changed by this step.
