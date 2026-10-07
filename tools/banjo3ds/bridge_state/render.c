#include "render.h"
#include <string.h>
int bridge_render_y(const BridgeModel *model,void *vertices,size_t vertex_count,
    size_t stride,size_t first,const uint16_t *ids,size_t count) {
    if(!model || !model->state || model->base.role!=1 || !vertices || !ids ||
       stride<3*sizeof(float) || first>vertex_count || count>vertex_count-first ||
       vertex_count>SIZE_MAX/stride)return -1;
    for(size_t i=0;i<count;i++)
        if(ids[i]<134 || ids[i]>165 || ids[i]>=model->base.vertex_count)return -1;
    int changed=0;
    for(size_t i=0;i<count;i++) {
        float y=bridge_component(&model->base,ids[i],1),old;
        uint8_t *p=(uint8_t *)vertices+(first+i)*stride+sizeof(float);
        memcpy(&old,p,sizeof(old));
        if(old!=y){memcpy(p,&y,sizeof(y));changed=1;}
    }
    return changed;
}
