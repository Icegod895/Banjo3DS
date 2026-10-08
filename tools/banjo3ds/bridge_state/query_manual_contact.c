/* Manual gate/recovery: shared immutable packets + sparse bridge coordinates.
 * The private contact primitive implementation is the proven D-B source. */
#include "../world_query/segment.h"
int bridge_segment(const BqModel *,const BqModel *,const float[3],float[3],uint32_t,BqHit *);
int16_t bridge_component(const BqModel *,unsigned,unsigned);
#define bq_segment bridge_segment
#define BQ_VERTEX_COMPONENT(m,v,a) bridge_component(m,v,a)
#include "../camera_manual/contact.c"
