# M4.9D.1 — isolated Spiral Mountain bridge world state

No viewer integration. This is the ordinary actor-0x3BA contract for canonical
NTSC map assets, not a general actor/mesh engine or a camera-wall-sticking fix.

## Original lifecycle and source evidence

- `assets/lvl_setup/071D.lvl_setup.bin`, NodeProp at **0xCAA**: category 6,
  actor **0x3BA**, position **(-168,1800,145)**. The independent tagged-cube
  parser freezes its complete 20-byte record and setup hash in the fixture.
- `src/core2/spawnqueue.c:267`: registration with `ACTOR_FLAG_UNKNOWN_19`.
  `code_A5BC0.c:1373` spawns category-6 setup records. The actor's position is
  NOT a transform origin; its update selects global mesh IDs.
- `code_DC4B0.c:10,33` binds/implements `func_80363500`.
  `ch/mole.c:488` ANDs nine `player_isAbilityUnlocked` calls; `code_7060.c:615`
  delegates to `ability_hasLearned`; `abilityprogress.c:99` tests
  `learnedAbilities`. This is **learned**, not used abilities, tutorial-dialog
  state or a camera condition. The actual enum is compiled from
  `include/core2/abilityprogress.h:23` by the independent reference.
- Required bits: BARGE 0, CLAW_SWIPE 4, CLIMB 5, FEATHERY_FLAP 7,
  FLAP_FLIP 8, HOLD_A_JUMP_HIGHER 10, RATATAT_RAP 11, ROLL 12, DIVE 15.
  Thus `(learned & 0x9DB1) == 0x9DB1`. No other ability matters.

Committed offsets **after the mesh update**, in world/model units:

| Lifecycle state | mesh 497 | mesh 498 | mesh 499 | actor remains |
|---|---:|---:|---:|---|
| Fresh model, before any mesh application | 0 | 0 | 0 | yes |
| First update, at least one required ability missing | 0 | 0 | -5000 | yes |
| All required abilities learned | -5000 | -5000 | 0 | no |

First update while all abilities are already learned schedules mesh497 and
requests despawn, then STILL executes the second `if`: schedules 498,499,497
and requests despawn again. Despawn during actor updates is deferred
(`code_9E370.c:1105`; bracketed by `spawnQueue_func_802C3A18`/flush), so this
must not be translated into an early return. Clearing bits after despawn
cannot restore the first configuration. While still alive but initialized,
missing abilities cause no new transform requests. Learning the final ability
schedules the completed configuration once, then despawns.

Fresh actor creation clears `volatile_initialized` (`code_9E370.c:833`).
Normal map loading recreates mesh states (`gsworld.c:211`, `mapModel.c:581`);
unloading frees model/mesh state (`gsworld.c:163,167`, `mapModel.c:562`).
The original model constructor copies original vertex values into mesh refs
(`code_B8080.c:151`). Save-state creation explicitly clears the actor's
volatile initialization bit (`code_9E370.c:1736`). Flag19 sets `unk58_1`
(:957), preventing restore's missing-saved-actor removal (:1845): a newly
spawned bridge controller can reapply progress even if the previous one had
already despawned. This module models fresh-map initialization, not the entire
save-state/cube loader. `gsworld_reload` itself skips setup loading; no claim
that invoking that otherwise unreferenced function alone respawns an actor.

Normal update order is important:

```
gsworld_update
  func_80330FF4 -> spawnQueue_func_802C39D4 -> func_803268B4
    actor 3BA tick: SCHEDULE offsets
  player update
  ncCamera_update: queries still read preceding committed mesh positions
  func_8034C9D4 -> func_8034E26C: APPLY scheduled offsets
```

Sources: `gsworld.c:315..338`, `code_A5BC0.c:1718`, `spawnqueue.c:422`,
`code_9E370.c:513`, `code_C5440.c:205`. `ActorInfo.unk18=0` gives this actor
no distance test in the ordinary update dispatcher. The caller must preserve
the actual actor/mesh phases; this module does not invent extra ticks during
pause, loading or another lifecycle. Finite nonnegative mesh dt is the domain.

There is one separate original writer: the **ANTI_TAMPER failure path** in
`src/SM/code_2900.c:6..21` can request 498=0/499=-5000. It is outside this
ordinary valid-game progress contract. We neither emulate checksum failure nor
pretend this progress module covers a tampered-game world. No additional
ordinary actor input is read by 3BA.

## Absolute transform and shared geometry

`code_C5440.c:154` assigns mesh IDs400..499 to transform type2.
`func_8034DEB4` (`code_C62B0.c:193`) requests vertical mode3 with **from=to**,
duration0; `func_8034DBB8` substitutes float32 `0.00001f`. Mesh update adds dt,
clamps elapsed, calls the callback, then marks completion. Even dt0 applies
the offset but leaves the request pending.

The exact callback (`code_C62B0.c:51`) is:

```
shift = (u16)(s32)(from + ((elapsed / duration) * (to - from)))
destinationY = (s16)(originalY + shift)
```

Float32 division/subtraction/multiply/add, signed truncation, unsigned16 shift
and final signed16 conversion are preserved. No cumulative displacement:
`originalY` comes from `BKModelVtxRef.v`, not the previously shifted vertex.
No runtime overflow occurs for these coordinates/offsets.

`model_transformMesh` (`code_B8080.c:27`) writes the model's live vertex list.
`mapModel_xlu_draw` (:351) and line/moving-sphere/sphere wrappers
(`mapModel.c:450,511,534`) use the same model/vertex list. Original collision
and rendering therefore share the transformed state. **Future integration
must feed both geometry consumers consistently**; this task changes neither.

## Exact membership and query representation

All affected vertices are in **14D0**, zero-based IDs:

- 497: 134,135,136,137
- 498: 150,151,152,153,154,155,156,157,158,159,160,161,162,163,164,165
- 499: 138,139,140,141,142,143,144,145,146,147,148,149

32 unique IDs. Ten unique collision records, **20 occurrences**, reference
these vertices: cell17 records119..128 and cell18 records153..162. Mesh497 has
two unique triangles/four occurrences; 499 has eight/16; 498 has **no collision
occurrences**. The frozen manifest includes every cell/index/vertex triple,
surface and flags, including duplicate occurrences, in original order.

`BridgeState` stores only three pending/applied offsets plus actor lifecycle.
`BridgeModel` borrows a validated immutable B3Q1 view and this shared state.
`bridge_component` changes only Y of those32 XLU IDs; every OPA coordinate,
all other XLU coordinates and all indices/records/flags/cells remain original.
Grid membership, bounds and global_norm are deliberately NOT rebuilt after
moving vertices, matching the original mesh callback. Probes at shifted
heights therefore retain Rare's original broadphase behavior.

`segment.c` and `contact.c` each have one compile-time coordinate-read hook.
Its default is the exact previous raw-load expression. Isolated namespaced
translation units under this directory reuse those SAME query/free-B sources
with the bridge reader; they are NOT in the viewer Makefile. No algorithms,
existing `BqModel` layout, camera formulas or packet bytes change. The
namespaced APIs accept only `BridgeModel.base` pointers. Caller retains both
packets and state for their entire query lifetime; no per-query copies.

## Independent proof and frozen corpus

`tests/bridge_reference.py` compiles the actual original actor, ability getter,
vertical setter, mesh update and vertex callback into the existing independent
original query/free-B oracle. Host pointer-width and model-storage adapters
are explicit. Unexpected nonvertical mesh/sound paths abort; no production
bridge or query algorithms are imported. Mesh membership comes from the raw
asset. No fixture depends on `/tmp`.

Coverage at **both -O0 and -O2**:

- Every lifecycle phase; zero/tiny/normal dt; repeated updates; progress change;
  all nine missing-bit cases and unrelated bits; despawn; fresh map reset.
- Every coordinate of both models, not just the32 changed vertices.
- **1,942 real-map primitive queries × 3 world states**, bit-exact endpoint,
  normal, occurrence/provenance/flags/surface; line/sphere/moving/gated queries.
- Three original M4.9D seeds ×3 states ×180 updates = **1,620 full free-B
  updates** per optimization level, including actual terrain-floor queries,
  contact traces, counters, rollback, accumulators and final orientation.
- Two-state tests have zero production/reference divergences. Static raw mode
  and unrelated geometry retain original results. Packet buffers remain intact.

These are explicit diagnostic player/floor inputs, **not recorded gameplay or
a recreation of the user's hardware route**. Zones are disabled in these
isolated B schedules; no new camera-node behavior is introduced.

| Seed | Missing-abilities first raw difference / max camera delta | All learned first raw difference / max delta |
|---|---|---|
| 109 | 72 / 37.2477866 | none / 0 |
| 110 | 75 / 23.4337793 | 110 / 5.0249369 |
| 111 | 56 / 11.3575705 | 57 / 315.5993537 |

These match M4.9D's independent transformed-world experiment. With the same
world state on both sides, all those production/reference discrepancies are
zero. The differences from the **raw static** world above are expected and
remain frozen. Rollback counts over180 updates:
raw109/110/111 = 70/74/126; missing abilities = 3/3/124; all learned =70/71/78.
No recovery success occurs in these particular seeds. This is **not** a proof
of general wall-sticking recovery.

`fixtures/bridge_state_golden.json` freezes complete32-vertex snapshots,
all20 occurrences, query-input/output hashes, whole-14D0 XYZ hashes, nine
complete-camera-stream hashes and comparison metrics. Packing: XYZ in asset
order as `>3h`; query results use existing `contact_corpus.pack_query`; complete
camera frames use existing `free_b_corpus.packed` (no padding).

| State | Whole-14D0 XYZ SHA256 | Query output SHA256 |
|---|---|---|
| raw | ae54f6440b669afa2861bacad0eee4b82ae7abcf969878c8fd654583a9641cfb | d310de93a3de0bbcf817ea8cfc1c163197b744e2afc039168a4812d6d530ab8c |
| missing abilities | 484c487e4f0cf579f6da7f230e61d576b5bcef51a64b88479418bda7986c1cb2 | 3c78df0b6dda225d23f8ce1d60573469c41fb47f61bb8aa255d8664fdadaf32a |
| all learned | 3c45b43edf3a8cba7870d0411efc515fd05dd47d678ab1bfda2e6690ad1789c0 | 96dd7bef87621e72fcc84caf50f0dce0f1cb057e4559d363509ab1a2edeec2c3 |

B3Q1 unchanged: OPA143,964 bytes
`59d398308ec5ed0fc249f684dfb6726bc77bf645dfd01a0a7976974fc80e6953`;
XLU14,580 bytes
`500d3ee02856c57f9bf379c3631514e36efb6019e4abd04453a6f26d3d86831f`.

## Costs and validation

Measured ARMv6K hard-float -O2, `-Wall -Wextra -Werror`, contract float flags:

- Bridge state **40 bytes**; each borrowed model view **40 bytes**, vs36 for
  original BqModel. Two views plus state =120 bytes, **48 bytes additional**
  over two original views. No per-vertex persistent allocation.
- Packet data added: **0 bytes**; neither complete packet nor vertex block
  is copied. No heap allocation, including init/query/update.
- `bridge.o`: **576 bytes .text**, 0 .rodata/.data/.bss.
- Isolated query objects: segment3,888 text+5 rodata; contact8,832+44;
  free-B928+0. All four new objects total **14,224 text +49 rodata** before
  linker GC. This deliberately separate testable variant reuses existing
  source, not a second hand-maintained collision implementation. If linked
  alongside the old path, that is the conservative extra object payload;
  final viewer linking/deduplication is outside this task.
- Existing contact scratch remains **8,000 bytes**, caller-owned. Bridge adds
  no per-query scratch buffer. GCC own stack frames: actor/mesh tick0,
  component8, open16; model query312 (old296), terrain adapter112 (old104),
  complete free-B wrapper488 unchanged. Conservative deepest contact path
  own-frame sum about1,616 bytes excluding caller storage/libm internals.
- **Actual current viewer ROM/RAM change: 0** — no new module linked.

Normal-default segment/contact ARM `.text` is byte-identical to the pre-task
sources, in addition to the existing functional goldens. The old sources were
reconstructed and checked against the pre-task SHA snapshots before compiling.
Full suite **301/301**; separate bridge suite7/7 after sourcing the ability enum
directly from its original header. ARM compilation zero warnings; diff/cached
whitespace checks clean. Existing fixtures, modelheader and3dsx hashes unchanged.
No staging, commit or push.

Run:

```
.venv/bin/python -B -m unittest discover -s tools/banjo3ds/tests -v
```

Not supported/implemented here: arbitrary mesh animations/callbacks, corrupted
ROM/anti-tamper state, generic save-state emulation, dynamic actor providers,
camera zones, viewport transitions, rendering updates or viewer integration.
