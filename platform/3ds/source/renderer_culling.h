#pragma once

#include <3ds/types.h>
#include <3ds/gpu/enums.h>

/* Same semantic bits as the exported N64 cull state; checked at the call site. */
enum {
    RENDERER_CULL_NONE = 0, RENDERER_CULL_FRONT = 1,
    RENDERER_CULL_BACK = 2, RENDERER_CULL_BOTH = 3,
    RENDERER_CULL_SKIP = -1
};

typedef enum {
    RENDERER_WINDING_NORMAL,   /* Proper LH debug view: front faces are CW. */
    RENDERER_WINDING_REVERSED  /* Z-reflected Rare RH view: fronts are CCW. */
} RendererWindingParity;

/* The only N64-to-PICA culling boundary. No camera-name dependence.
 * Current model transforms have positive determinant. A future reflecting
 * model transform would also have to contribute to this parity.
 * See tools/banjo3ds/CULLING_PARITY.md for the projection/visibility proof. */
static inline int rendererCullMode(unsigned int materialCull,
    RendererWindingParity parity)
{
    switch (materialCull) {
        case RENDERER_CULL_NONE:
            return GPU_CULL_NONE;
        case RENDERER_CULL_BACK:
            return parity == RENDERER_WINDING_REVERSED
                ? GPU_CULL_BACK_CCW : GPU_CULL_FRONT_CCW;
        case RENDERER_CULL_FRONT:
            return parity == RENDERER_WINDING_REVERSED
                ? GPU_CULL_FRONT_CCW : GPU_CULL_BACK_CCW;
        default: /* BOTH, or invalid data: never submit a visible draw. */
            return RENDERER_CULL_SKIP;
    }
}
