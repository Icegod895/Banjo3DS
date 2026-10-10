/* Isolated host composition. Reuse accepted camera math privately; no change
 * to its viewer ABI, object or call graph. See README for link boundary. */
#define banjo_camera_math_init bm_private_math_init
#define banjo_camera_init bm_private_init
#define banjo_camera_prepare bm_private_prepare
#define banjo_camera_prepare_selected bm_private_prepare_selected
#define banjo_camera_finish bm_private_finish
#define banjo_camera_update bm_private_update
#define banjo_camera_project bm_private_project
#define banjo_camera_set_lead_amplitudes bm_private_set_lead
#include "../camera/camera.c"
#undef banjo_camera_math_init
#undef banjo_camera_init
#undef banjo_camera_prepare
#undef banjo_camera_prepare_selected
#undef banjo_camera_finish
#undef banjo_camera_update
#undef banjo_camera_project
#undef banjo_camera_set_lead_amplitudes
#include "manual.h"

static void get_focus(BmState *s,const BanjoCameraInput *in){
    base_focus(in,s->camera.focus);
    if(s->focus_mode!=1)for(int i=0;i<3;i++)s->camera.focus[i]+=s->camera.lead[i];
}
static float horizontal_distance(const float *a,const float *b){
    float x=a[0]-b[0],z=a[2]-b[2];return sqrtf(x*x+z*z);
}
static void r_snapshot(BmState *s,const BanjoCameraMath *math,const BanjoCameraInput *in){
    get_focus(s,in);s->r_radius=horizontal_distance(s->camera.position,s->camera.focus);
    s->r_orbit=heading(math,s->camera.position[0]-s->camera.focus[0],s->camera.position[2]-s->camera.focus[2]);
    s->r_velocity=0;
}
static void state(BmState *s,const BanjoCameraMath *math,const BanjoCameraInput *in,int n){
    if(s->camera.state==n)return;
    /* ncDynamicCamera_setState ends state 0x12 before the next init.
     * Engagement writes 0x12 directly and does not pass through here. */
    if(s->camera.state==0x12){br_end(s);bm_private_set_lead(110.f,180.f);}
    if(n==11){
        s->focus_mode=2;get_focus(s,in);s->position_gain=3;s->position_response=8;s->rotation_gain=5;s->rotation_response=10;
        s->camera.orbit_yaw=heading(math,s->camera.position[0]-s->camera.focus[0],s->camera.position[2]-s->camera.focus[2]);
    }else if(n==17)s->focus_mode=1;
    else if(n==19){
        s->position_gain=5;s->position_response=8;s->rotation_gain=8;s->rotation_response=15;s->focus_mode=6;
        s->viewport_remaining=s->viewport_duration=.5f;s->viewport_state=1;
        memcpy(s->viewport_offset,s->camera.position,12);memcpy(s->viewport_angles,s->camera.rotation,12);
        r_snapshot(s,math,in);s->r_target=angle(in->visible_yaw+180.0);
    }
    s->camera.state=n;
}
void bm_init(BmState *s,const BanjoCameraMath *m,const BanjoCameraInput *in,const float eye[3],const float rot[3]){
    memset(s,0,sizeof(*s));bm_private_init(&s->camera,m,in,eye,rot);bz_init(&s->zones);
    s->focus_mode=2;s->c_radius=100;s->zoom_timer=.5f;s->radius=850;s->height=375;
    s->position_gain=3;s->position_response=8;s->rotation_gain=5;s->rotation_response=10;
    memcpy(s->viewport_position,eye,12);memcpy(s->viewport_rotation,rot,12);
    br_reset(&s->rail);
}
size_t bm_state_size(void){return sizeof(BmState);}
static void lead_update(BmState *s,const BanjoCameraInput *in){
    BanjoCamera *c=&s->camera;float dx=in->player[0]-c->position[0],dz=in->player[2]-c->position[2];
    float near_amp=110.f,far_amp=180.f;
    if(br_bound()){near_amp=s->rail.lead_near;far_amp=s->rail.lead_far;}
    float amplitude=map(fabsf((float)(angle(c->rotation[1]-in->visible_yaw)-180.0)),0,180,near_amp,far_amp),lead[3];
    vector(lead,in->visible_yaw,map(sqrtf(dx*dx+dz*dz),300,450,0,amplitude));
    for(int i=0;i<3;i++){float d=lead[i]-c->lead[i];d*=.08f;c->lead[i]+=d;}
    get_focus(s,in);
}
static void zoom_button(BmState *s,unsigned edges,unsigned enabled){
    if(s->zoom_timer==0 && (edges&BM_DOWN) && (enabled&32)){
        s->camera.preset=s->camera.preset==3?1:s->camera.preset+1;s->zoom_timer=.4f;
    }
}
static int request(BmState *s,const BanjoCameraMath *m,const BanjoCameraInput *in,float turn,
    const BqModel *o,const BqModel *x,BcScratch *scratch,BcTrace *trace){
    get_focus(s,in);s->c_radius=horizontal_distance(s->camera.position,s->camera.focus);
    s->c_orbit=heading(m,s->camera.position[0]-s->camera.focus[0],s->camera.position[2]-s->camera.focus[2]);
    s->c_step=0;s->c_target=angle(s->c_orbit+turn);s->c_complete=0;
    float part=turn/5.0,a=angle(s->c_orbit+part),candidate[3];a*=3.141592654/180.0;
    candidate[0]=trig(a,false)*s->c_radius;candidate[2]=trig(a,true)*s->c_radius;
    candidate[0]+=s->camera.focus[0];candidate[2]+=s->camera.focus[2];candidate[1]=s->camera.position[1];
    int ok=bm_gate(o,x,s->camera.position,candidate,scratch,trace);
    if(ok>0){state(s,m,in,10);s->camera.mode=7;}return ok;
}
static int rotate_buttons(BmState *s,const BanjoCameraMath *m,const BanjoCameraInput *in,unsigned edges,unsigned enabled,
    const BqModel *o,const BqModel *x,BcScratch *scratch,BcTrace *trace){
    int r=0;
    if((edges&BM_LEFT) && (enabled&1))r=request(s,m,in,-45,o,x,scratch,trace);
    if(r!=0)return r;
    if((edges&BM_RIGHT) && (enabled&2))r=request(s,m,in,45,o,x,scratch,trace);
    return r;
}
static void r_angle(BmState *s,float dt){
    if(s->r_target==s->r_orbit){s->r_velocity=0;return;}
    float d=delta(s->r_target,s->r_orbit);
    if(fabsf(d)<100){
        /* ml_mapAbsRange_f calls ml_map_f with negative ranges too. */
        float v=((d-0)/(d<0?-100.f:100.f))*((d<0?-160.f:160.f)-(d<0?-10.f:10.f))+(d<0?-10.f:10.f);
        s->r_velocity=v;
    }else{
        float a=800.f*dt;if(d<0)a=-a;s->r_velocity+=a;
        if(s->r_velocity< -160)s->r_velocity=-160;else if(s->r_velocity>160)s->r_velocity=160;
    }
    float step=s->r_velocity*dt;
    if(fabsf(step)>fabsf(d) && step*d>0){s->r_velocity=0;s->r_orbit=s->r_target;step=0;}
    s->r_orbit=angle(s->r_orbit+step);
}
static void c_angle(BmState *s,float dt,int vi){
    float d=delta(s->c_target,s->c_orbit),r=(d*dt*50.f)-s->c_step;
    s->c_step=(.0333*r)*3.f;
    if(fabsf(d)<.5 || (fabsf(s->c_step)>fabsf(d) && d*s->c_step>0)){s->c_step=0;s->c_orbit=s->c_target;}
    s->c_orbit=angle(s->c_orbit+s->c_step);s->c_complete=fabsf(s->c_target-s->c_orbit)<.5;
    s->c_radius=horizontal_distance(s->camera.position,s->camera.focus);
    for(int i=0;i<vi*5;i++){
        float error=s->radius-s->c_radius,diff=error*.01f-s->c_radius_step;
        s->c_radius_step+=diff*.008f;
        if(overshot(s->c_radius_step,error)){s->c_radius_step=0;s->c_radius=s->radius;break;}
        s->c_radius=s->c_radius_step+s->c_radius;
    }
}
static void add_trace(BcTrace *a,const BcTrace *b){
    a->sphere_calls+=b->sphere_calls;a->line_calls+=b->line_calls;a->moving_calls+=b->moving_calls;a->gated_calls+=b->gated_calls;
    a->obstruction_calls+=b->obstruction_calls;a->recovery_attempts+=b->recovery_attempts;a->changed|=b->changed;a->recovered|=b->recovered;
    memcpy(a->pushed_previous,b->pushed_previous,12);memcpy(a->extended_end,b->extended_end,12);memcpy(a->subtracted_end,b->subtracted_end,12);
}
static bool manual_dynamic(BmState *s,const BanjoCameraMath *m,const BanjoCameraInput *in,
    const BqModel *o,const BqModel *x,const float target[3],BcScratch *scratch,BcTrace *trace){
    BanjoCamera *c=&s->camera;bool r=c->state==19;
    lead_update(s,in);if(!r && s->c_complete)return true;
    float old[3],offset[3],radius,height;memcpy(old,c->position,12);
    if(r){r_angle(s,in->dt);radius=horizontal_distance(old,c->focus);radius=radius+(s->radius-radius)*in->dt*2;}
    else {c_angle(s,in->dt,in->vi_frames);radius=s->c_radius;}
    vector(offset,r?s->r_orbit:s->c_orbit,radius);
    height=in->player[1]-in->floor_height>130.f?in->player[1]+s->height-130.f:s->height+in->floor_height;
    float clearance=in->floor_under_camera+35.f+20.f;if(height<clearance)height=clearance;
    for(int i=0;i<3;i++)c->position[i]=c->focus[i]+offset[i];
    c->position[1]=old[1]+(height-old[1])*in->dt*2;
    BcTrace contact_trace={0};int changed=bc_contact(o,x,old,c->position,scratch,&contact_trace);
    if(changed<0)return false;
    add_trace(trace,&contact_trace);
    if(!r && changed){s->c_complete=1;s->c_radius_step=0;}
    int recovered=0;
    if(!r || changed){
        BcState st={.counter=s->post.obstruction_counter};
        memcpy(st.position_step,c->position_step,12);memcpy(st.angular_step,c->angular_step,12);
        recovered=bm_obstruction(o,x,c->position,target,r?0:delta(s->c_target,s->c_orbit)>0?2:3,&st,scratch,trace);
        if(recovered<0)return false;
        s->post.obstruction_counter=st.counter;
        memcpy(c->position_step,st.position_step,12);memcpy(c->angular_step,st.angular_step,12);
    }
    if(r && recovered)r_snapshot(s,m,in);
    if(!r && recovered)s->c_radius_step=0;
    float angles[3];look(m,c->focus,c->position,angles);
    if(!r && (changed || recovered))s->c_radius=horizontal_distance(c->position,c->focus);
    if(!r && recovered){s->c_complete=1;memcpy(c->rotation,angles,12);return true;}
    angles[0]=c->rotation[0]+delta(angles[0],c->rotation[0])*in->dt*4;
    if(!r)angles[1]=c->rotation[1]+delta(angles[1],c->rotation[1]);
    memcpy(c->rotation,angles,12);if(!r && s->c_complete)s->c_radius_step=0;
    return true;
}
static void viewport(BmState *s,float dt){
    memcpy(s->viewport_position,s->camera.position,12);memcpy(s->viewport_rotation,s->camera.rotation,12);
    if(!s->viewport_state)return;
    if(s->viewport_state==1){
        for(int i=0;i<3;i++)s->viewport_offset[i]-=s->camera.position[i];
        for(int i=0;i<2;i++)s->viewport_angles[i]=delta(s->viewport_angles[i],s->camera.rotation[i]);
        s->viewport_angles[2]=0;s->viewport_state=2;
    }
    s->viewport_remaining-=dt;
    if(s->viewport_remaining<=0){s->viewport_state=0;return;}
    float f=map(s->viewport_remaining,0,s->viewport_duration,0,1);
    for(int i=0;i<3;i++){s->viewport_position[i]+=s->viewport_offset[i]*f;s->viewport_rotation[i]+=s->viewport_angles[i]*f;}
    for(int i=0;i<2;i++)s->viewport_rotation[i]=angle(s->viewport_rotation[i]);
    s->viewport_rotation[2]=0;
}
bool bm_update(BmState *state_in,const BanjoCameraMath *m,const BzData *data,const BanjoCameraInput *in,
    uint32_t buttons,uint32_t enabled,const BqModel *o,const BqModel *x,const float target[3],BcScratch *scratch,BmTrace *out){
    if(!state_in || !m || !data || !in || !o || !target || !scratch || !out || buttons>15
       || !isfinite(in->dt) || in->dt<0 || in->dt>.05f || in->vi_frames<1 || in->vi_frames>15)return false;
    if(state_in->camera.preset<1 || state_in->camera.preset>3 || !data->nodes || !data->groups || !data->triggers
       || !isfinite(in->floor_height) || !isfinite(in->floor_under_camera)
       || !isfinite(in->visible_yaw) || fabsf(in->visible_yaw)>36000)return false;
    for(int i=0;i<3;i++)if(!isfinite(in->player[i]) || fabsf(in->player[i])>20000)return false;
    BmState s=*state_in;BmTrace t={0};unsigned edges=buttons&~s.buttons;s.buttons=buttons;
    s.zoom_timer-=in->dt;if(s.zoom_timer<0)s.zoom_timer=0;
    if(in->stable)memcpy(s.camera.stable_position,in->player,12);
    int node=bz_select(&s.zones,data,s.camera.stable_position);s.camera.node=node;
    bool zoom=false;
    if(node<0)s.zones.profile=0;
    else{
        if((size_t)node>=data->node_count)return false;
        if(data->nodes[node].type==3){zoom=true;s.zones.last_zoom=node;}
        else if(data->nodes[node].type==4 && data->nodes[node].profile==1)s.zones.profile=1;
        else return false;
    }
    static const float radii[2][3]={{550,850,1100},{800,950,1100}},heights[2][3]={{175,375,675},{375,525,675}};
    if(!zoom){s.radius=radii[s.zones.profile][s.camera.preset-1];s.height=heights[s.zones.profile][s.camera.preset-1];}
    BanjoCameraZoom empty={0};const BanjoCameraZoom *z=s.zones.last_zoom<0?&empty:&data->nodes[s.zones.last_zoom].zoom;
    if(z->flags&1)return false;
    /* Unbound frames keep the free-camera 110/180 statics. A bound reject
     * writes 80/200 onto the rail before this second store. */
    if(!br_bound())bm_private_set_lead(110.f,180.f);
    else bm_private_set_lead(s.rail.lead_near,s.rail.lead_far);
    if(br_bound()){
        if(br_triggers(&s,m,in,o,x)<0)return false;
        bm_private_set_lead(s.rail.lead_near,s.rail.lead_far);
    }
    /* Mode 0xA owns this frame, including the actor-0x2A frame that drops
     * back to mode 2 before the dynamic update. C-up is not one of these bits. */
    bool suppress=br_bound() && s.camera.mode==0xA;
    if(suppress && s.rail.actor<1)s.camera.mode=2;
    if(!suppress){
        if(zoom){state(&s,m,in,17);s.camera.mode=9;s.position_gain=z->position_gains[0];s.position_response=z->position_gains[1];s.rotation_gain=z->rotation_gains[0];s.rotation_response=z->rotation_gains[1];}
        else if(s.camera.mode==9)s.camera.mode=2;
        else{
            int rotated=0;
            if(s.camera.mode==4){
                rotated=rotate_buttons(&s,m,in,edges,enabled,o,x,scratch,&t.contact);
                if(rotated==0){zoom_button(&s,edges,enabled);if(buttons&BM_R)s.r_target=angle(in->visible_yaw+180.0);else if(fabsf(delta(s.r_target,s.r_orbit))<4.0)s.camera.mode=2;}
            }else if(s.camera.mode==7){
                zoom_button(&s,edges,enabled);rotated=rotate_buttons(&s,m,in,edges,enabled,o,x,scratch,&t.contact);
                if(rotated==0 && s.c_complete)s.camera.mode=2;
            }else if(s.camera.mode==2){
                if(buttons&BM_R){state(&s,m,in,19);s.camera.mode=4;zoom_button(&s,edges,enabled);}
                else {rotated=rotate_buttons(&s,m,in,edges,enabled,o,x,scratch,&t.contact);zoom_button(&s,edges,enabled);if(rotated==0)state(&s,m,in,11);}
            }else return false;
            if(rotated<0)return false;
        }
    }
    if(br_bound() && s.camera.state==0x12)br_drive(&s,m,in);
    else if(s.camera.state==19 || s.camera.state==10){
        if(!manual_dynamic(&s,m,in,o,x,target,scratch,&t.contact))return false;
    }else if(s.camera.mode==0xA)return false;
    else{
        BanjoCameraPhase phase;BanjoCamera input=s.camera;
        if(input.state==17 && !zoom)input.mode=9;
        if(!bm_private_prepare_selected(&phase,&input,m,z,in,node,zoom,s.radius,s.height))return false;
        if(!bc_free_b_finish_phase(&s.camera,&s.post,m,z,in,&phase,o,x,target,scratch,&t.free_b))return false;
        add_trace(&t.contact,&t.free_b.contact);
    }
    viewport(&s,in->dt);*state_in=s;*out=t;return true;
}
