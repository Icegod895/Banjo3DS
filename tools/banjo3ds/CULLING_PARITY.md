# M4.8B.10 — renderer winding boundary

This step does not integrate the Rare camera. The active debug view still uses
NORMAL parity. Culling belongs to the draw's N64 state, not the texture/material.

## Geometric contract

Use column positions, ordered triangle `(p0,p1,p2)`, and unnormalized normal
`n = (p1-p0) cross (p2-p0)`. Positive projected signed area means CCW in PICA
viewport coordinates (not downward-positive screenshot pixel coordinates).

For the linear part L of a model/view transform:

```
(L*a) cross (L*b) = det(L) * transpose(inverse(L)) * (a cross b)
det(L) = det(view) * det(model)
```

Translations do not affect this determinant. For an orthographic projection
with positive horizontal/vertical scales sx, sy, projected signed area is
`sx*sy * (cross(L*edge1,L*edge2)).z`. For our LH perspective, all three view Z
values must be positive (W=Z). With world vertices, world eye E and view V:

```
signedArea = sx*sy * det(V) * dot(n, p0-E) / (z0*z1*z2)
```

Thus for front-facing world geometry (normal toward the eye), the current
proper LH view produces CW and the Z-reflected Rare view produces CCW.
The cross-product identity includes any additional model reflection: a negative
model determinant would require another parity inversion relative to local
front-face semantics. Current models do not introduce one.

**Determinants alone do not predict which side an arbitrary camera sees.**
Two unrelated eyes can see opposite sides. The regression compares matching
eye/forward directions. For debug `D=Rx(p)*Ry(y)` and Rare angles `(p,180-y)`,
the converted Rare matrix is `diag(-1,1,1)*D`: same forward/up, opposite right.
Projected areas consequently have opposite signs, even with ortho versus
perspective, when the eye is on the same side as the orthographic viewing ray.
Tests place each triangle's centroid on that common ray and keep all W positive.
Degenerate/edge-on triangles have no stable front/back sign and are not evidence
of a parity mismatch. Clipping does not add a reflection; the proof must not be
applied by dividing un-clipped vertices with mixed-sign W.

## Citro3D boundary and projection

Installed libctru `include/3ds/gpu/enums.h:302` defines NONE=0,
FRONT_CCW=1, BACK_CCW=2. These names identify the culled side:

| PICA value | Result |
|---|---|
| 0 | keep both windings |
| 1 / GPU_CULL_FRONT_CCW | discard CCW; keep CW |
| 2 / GPU_CULL_BACK_CCW | discard CW; keep CCW |

Citro3D [effect.c](https://github.com/devkitPro/citro3d/blob/master/source/effect.c)
stores the enum directly and writes its low two bits to FACECULLING_CONFIG.
Installed `libcitro3d.a` disassembly agrees. Independently, Azahar's
[RasterizerRegs::CullMode](https://github.com/azahar-emu/azahar/blob/master/src/video_core/pica/regs_rasterizer.h)
names values 1/2 KeepClockWise/KeepCounterClockWise.

Citro3D [mtx_orthotilt.c](https://github.com/devkitPro/citro3d/blob/master/source/maths/mtx_orthotilt.c)
uses XY coefficients `[[0,2/(top-bottom)],[2/(left-right),0]]`.
[mtx_persptilt.c](https://github.com/devkitPro/citro3d/blob/master/source/maths/mtx_persptilt.c)
uses `[[0,cot(fov/2)],[-cot(fov/2)/aspect,0]]`, and LH W=Z.
Both XY determinants are positive for ordered extents/positive aspect. The
quarter-turn tilt adds **no** winding inversion. Perspective PICA depth maps
near/far to -1/0; neither its depth coefficients nor depth-test direction
enter the XY signed area. The existing shader simply applies projection*view.
The display transfer has FLIP_VERT(0); presentation is not a culling operation.
No FOV, aspect, projection, viewport or shader setting changes in this step.

## One mapping, no camera-name checks

`platform/3ds/source/renderer_culling.h:rendererCullMode()` returns the actual
GPU enum, or SKIP for BOTH. Exported cull-bit values are checked at compile time.

| N64 draw state | NORMAL (+1 debug view) | REVERSED (-1 Rare view) |
|---|---|---|
| NONE | GPU_CULL_NONE | GPU_CULL_NONE |
| BACK | GPU_CULL_FRONT_CCW | GPU_CULL_BACK_CCW |
| FRONT | GPU_CULL_BACK_CCW | GPU_CULL_FRONT_CCW |
| BOTH | skip draw | skip draw |

The renderer calls this once at its existing culling boundary. NORMAL remains
the only active view parity. No vertex/index reversal and no geometry changes.
Future camera integration must supply REVERSED alongside the proven converted
view; selecting perspective alone is not the parity criterion.

## Model audit and real corpus

Map OPA/XLU use the view directly (`main.c:sceneRender`), hence model determinant
1. Actor `movementActorMatrix` uses T*Ry, whose determinant is
`cos(yaw)^2 + sin(yaw)^2 = 1`; translation, player movement and yaw do not flip it.
Tests execute this actual C routine for nine yaw values at -O0/-O2. Baked bone
deformations are already part of the triangle stream; they are not an extra
runtime model reflection. Future negative scaling is outside this contract.

The corpus decodes the actual assets, including the proven static idle pose:

| Part | Triangles | Materials used | Draws | BACK | NONE |
|---|---:|---:|---:|---:|---:|
| 14CF OPA | 3136 | 417 | 436 | 3136 | 0 |
| 034D idle | 695 | 16 + untextured | 28 | 695 | 0 |
| 14D0 XLU | 369 | 36 | 46 | 170 | 199 |

All 4200 triangles are nondegenerate. No actual FRONT or BOTH occurs; tests
explicitly exercise these states synthetically on the same real geometry.
Five pitches and four yaws cover horizontal, vertical and sloped faces from
both sides. Banjo additionally uses world yaw 0/90/145. Total: 111800 paired
orientation cases, with exactly edge-on cases excluded from signed-area claims.
Frozen totals: 54059 front-facing, 53954 back-facing and 3787 edge-on cases.
Every remaining case checks the independent determinant formula, opposite
projected area signs, and identical semantic retained/culled decisions.
The original plateau triangle at emitted vertex 3240 freezes signed areas
`-0.03703703703703704` and `+0.22645896511239097` for a matched overhead view.

These are geometric/enum correctness tests, not pixel-exact PICA rasterization
tests near subpixel or clipping degeneracies. No hardware visual claim is added.
