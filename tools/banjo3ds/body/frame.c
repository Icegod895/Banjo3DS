#include "frame.h"
int bp_frame_resolve(const BpFrameContext *c,BgFrame *frame,uint32_t identity) {
    if(!c || !c->clock || !c->history || !c->phase || !c->opa || !c->xlu ||
       !c->math || !c->scratch || !frame)return -1;
    BqFloorBridge *clock=c->clock;
    if(!clock->initialized || !clock->active || clock->frame!=identity ||
       clock->next_ordinal!=0 || c->opa->state!=c->xlu->state || !c->opa->state)
        return -1;
    int result=bp_resolve(c->history,c->phase,frame,&clock->floor,c->opa,c->xlu,
        c->math,bq_bridge_parity(clock),c->scratch,&c->scratch->trace);
    if(result==1) {
        /* Accounting for queries ALREADY performed inside E.2, never callbacks
         * or floor queries for accepted/fallback positions. Internal working
         * floor history feeds each next iteration; publish once to its owner. */
        clock->next_ordinal=c->scratch->trace.iterations;
    }
    return result;
}
