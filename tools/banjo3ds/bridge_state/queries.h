#ifndef BANJO_BRIDGE_QUERIES_H
#define BANJO_BRIDGE_QUERIES_H
#include "bridge.h"
#include "../world_query/floor_bridge.h"
#include "../camera_contact/free_b.h"
#include "../camera_zones/zones.h"
/* Only BridgeModel.base pointers are valid for these isolated entry points.
 * Other inputs/outputs retain the original query API and math contracts. */
int bridge_segment(const BqModel *,const BqModel *,const float[3],float[3],uint32_t,BqHit *);
int bridge_camera_terrain(const BqModel *,const BqModel *,const float[3],float *);
int bridge_sphere(const BqModel *,const BqModel *,const float[3],float,uint32_t,BqHit *);
int bridge_moving(const BqModel *,const BqModel *,const float[3],float[3],float,int,uint32_t,BcScratch *,BqHit *);
int bridge_gated(const BqModel *,const BqModel *,const float[3],float[3],float,int,uint32_t,BcScratch *,BqHit *);
int bridge_contact(const BqModel *,const BqModel *,float[3],float[3],BcScratch *,BcTrace *);
int bridge_state_b(const BqModel *,const BqModel *,float[3],float[3],const float[3],BcState *,BcScratch *,BcTrace *);
bool bridge_free_b_update(BanjoCamera *,BcFreeBState *,const BanjoCameraMath *,
 const BanjoCameraZoom *,const BanjoCameraTrigger *,size_t,const BanjoCameraInput *,
 const BqModel *,const BqModel *,const float[3],BcScratch *,BcFreeBTrace *);
bool bridge_free_b_rollback(float *,const float[3],const float[3],float[3],float *);
int bridge_cadence_candidate(BqFloorBridge *,const BqModel *,const BqModel *,const float[3],uint32_t);
bool bridge_bz_update(BzState *,BanjoCamera *,BcFreeBState *,const BanjoCameraMath *,
 const BzData *,const BanjoCameraInput *,bool,const BqModel *,const BqModel *,
 const float[3],BcScratch *,BcFreeBTrace *);
#endif
