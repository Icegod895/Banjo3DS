/* Bridge-coordinate query variant shared by host tests and runtime.
 * Original algorithms stay shared; only the coordinate-read boundary changes. */
#include "query_names.h"
#include "../world_query/segment.h"
int16_t bridge_component(const BqModel *, unsigned, unsigned);
#define BQ_VERTEX_COMPONENT(m,v,a) bridge_component((m),(v),(a))
#include "../world_query/segment.c"
