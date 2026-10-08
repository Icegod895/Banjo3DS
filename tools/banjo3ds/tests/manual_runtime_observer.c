/* Test-only observer and accepted M4.10C neutral-camera comparator.
 * Neither this trace storage nor the selector bypass is linked into the viewer. */
#include "camera_runtime.h"
#include <string.h>
static BmTrace observed;
static int legacy;
void runtime_legacy_camera(int enabled){legacy=enabled;}
void runtime_manual_trace(BmTrace *out){*out=observed;}
bool __real_bm_update(BmState *,const BanjoCameraMath *,const BzData *,const BanjoCameraInput *,
    uint32_t,uint32_t,const BqModel *,const BqModel *,const float[3],BcScratch *,BmTrace *);
bool __wrap_bm_update(BmState *s,const BanjoCameraMath *m,const BzData *d,const BanjoCameraInput *in,
    uint32_t buttons,uint32_t enabled,const BqModel *opa,const BqModel *xlu,const float target[3],BcScratch *scratch,BmTrace *trace){
    bool ok;
    if(legacy){
        memset(trace,0,sizeof(*trace));
        ok=bridge_bz_update(&s->zones,&s->camera,&s->post,m,d,in,false,opa,xlu,target,scratch,&trace->free_b);
        if(ok){memcpy(s->viewport_position,s->camera.position,12);memcpy(s->viewport_rotation,s->camera.rotation,12);}
    }else ok=__real_bm_update(s,m,d,in,buttons,enabled,opa,xlu,target,scratch,trace);
    if(ok)observed=*trace;else memset(&observed,0,sizeof(observed));
    return ok;
}
