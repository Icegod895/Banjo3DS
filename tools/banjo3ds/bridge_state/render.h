#ifndef BANJO_BRIDGE_RENDER_H
#define BANJO_BRIDGE_RENDER_H
#include "bridge.h"
/* CPU publication into an existing XYZ/UV/RGBA VBO. Caller must synchronize
 * with the GPU first, then flush this range if >0. -1 rejects the entire write.
 * Absolute original Y + committed mesh offset: safe after skipped draw frames. */
int bridge_render_y(const BridgeModel *,void *vertices,size_t vertex_count,
    size_t stride,size_t first,const uint16_t *source_ids,size_t count);
#endif
