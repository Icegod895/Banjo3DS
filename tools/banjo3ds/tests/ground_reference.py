"""E.1 independent decomp floor phase. No production ground/query imports.

Compile original persistent floor/segment, func_8029350C, player_shouldFall and
bsjump_fall_init. Candidate arithmetic is the verbatim vertical/position tail
of __baphysics_update_normal; horizontal post-response velocity is an input.
Host pointer ABI/zeroed diagnostic padding follow floor_state_reference.
"""
import ctypes as C
import functools
from pathlib import Path
import subprocess
import tempfile
import floor_state_reference as floor
from segment_reference import ROOT, FLAGS, function
F=C.c_float

@functools.lru_cache(None)
def library(opt):
    base=floor.library(opt);text=(Path(base._tmp.name)/'ref.c').read_text()
    text+=function('src/core1/ml.c','ml_vec3f_scale')
    text+=r'''
#define TRUE 1
#define FALSE 0
typedef struct {float position[3],vy,height;uint32_t grounded,falling;} Ground;
typedef struct {float previous[3],candidate[3],requested[3],normal[3];uint32_t grounded;} Frame;
static Ground *gs;
static float D_8037C238[3];static u8 D_8037C279;
#define D_8037C200 state
int baMarker_8028D694(void){return 0x400000;}
float playerPosition_getY(void){return gs->position[1];}
float func_80294438(void){return gs->height;}
static int injected;
static void phase_floor_update(struct0 *s){if(!injected)func_8031C44C(s);}
#define func_8031C44C phase_floor_update
'''
    text+=function('src/core2/code_C4B0.c','func_8029350C')
    text+='\n#undef func_8031C44C\n'
    text+=function('src/core2/playerutils.c','player_shouldFall')
    # Compile actual fall initializer with observable animation/control calls.
    text+=r'''
typedef int AnimCtrl;static AnimCtrl ctrl;static int D_8037D4C0;
static float fall_config[5];static int set_velocity_calls;
#define BA_FLAG_7_TOUCHING_JIGGY 7
#define BS_12_BFLIP 18
#define ASSET_B0_ANIM_BSJUMP_FALL 176
#define YAW_STATE_1_DEFAULT 1
#define BA_PHYSICS_AIRBORN 6
static AnimCtrl *baanim_getAnimCtrlPtr(void){return &ctrl;}
static int baflag_isTrue(int x){(void)x;return 0;} /* ordinary, no jiggy */
static float baphysics_get_vertical_velocity(void){return gs->vy;}
static void baphysics_set_vertical_velocity(float v){gs->vy=v;set_velocity_calls++;}
static int bs_getPrevState(void){return 1;} /* ordinary stand/walk, not backflip */
static void anctrl_reset(AnimCtrl*p){(void)p;}
static void anctrl_setSmoothTransition(AnimCtrl*p,int x){(void)p;fall_config[0]=x;}
static void anctrl_setIndex(AnimCtrl*p,int x){(void)p;fall_config[1]=x;}
static void anctrl_setTransitionDuration(AnimCtrl*p,float x){(void)p;fall_config[2]=x;}
static void anctrl_setDuration(AnimCtrl*p,float x){(void)p;fall_config[3]=x;}
static void anctrl_start(AnimCtrl*p,const char*s,int l){(void)p;(void)s;(void)l;}
typedef int BaPhysicsType;
#define BA_PHYSICS_TRANSFORM 11
#define BA_PHYSICS_GOTO 12
static int baphysics_type;static float D_8037C4FC,s_next_position[3],D_8037C500;
static struct {int state;} baphysics_goto;
'''
    text+=function('src/core2/ba/physics.c','baphysics_set_type')
    text+='static void code_14420_setUpdateTypes(int a,int b,int c,int d){(void)a;(void)b;(void)c;baphysics_set_type(d);fall_config[4]=baphysics_type;}\n'
    text+=function('src/core2/bs/jump.c','bsjump_fall_init')
    text+=r'''
int ground_ref_state(Ground*s){gs=s;if(!s->falling&&player_shouldFall()){bsjump_fall_init();s->falling=1;return 1;}return 0;}
void ground_ref_fall_config(float*out,int*calls){memcpy(out,fall_config,sizeof(fall_config));*calls=set_velocity_calls;}
void ground_ref_candidate(Ground*s,float*h,float dt,Frame*f){
 memset(f,0,sizeof(*f));memcpy(f->previous,s->position,12);f->grounded=s->grounded;
 float s_player_velocity[3]={h[0],s->vy,h[1]};float s_delta_position[3]={h[0],0,h[1]};
 float s_next_position[3];memcpy(s_next_position,s->position,12);
 float s_gravity=-2700.f,s_terminal_velocity=-4000.f;
#define time_getDelta() dt
'''
    body=function('src/core2/ba/physics.c','__baphysics_update_normal')
    text+=body[body.index('    //update velocity for gravity'):body.rfind('}')]
    text+=r'''
#undef time_getDelta
 s->vy=s_player_velocity[1];memcpy(f->candidate,s_next_position,12);
 for(int i=0;i<3;i++)f->requested[i]=f->candidate[i]-f->previous[i];
}
void ground_ref_resolve(Ground*s,Frame*f,int use_query,float height,float*n,unsigned frame_parity){
 parity=frame_parity;ncalls=0;gs=s;injected=!use_query;D_8037C279=f->grounded;
 memcpy(D_8037C238,f->requested,12);
 if(injected){state->posX=height;memcpy(&state->normX,n,12);}
 func_8029350C(f->candidate);
 memcpy(f->normal,&state->normX,12);s->height=state->posX;s->grounded=D_8037C279;
 memcpy(s->position,f->candidate,12);
'''
    # Original normal post-contact velocity block, no water or stuck override.
    src=function('src/core2/code_C4B0.c','func_80293F0C')
    start=src.index('        if (baphysics_get_vertical_velocity() < 0.0f)')
    end=src.index('\n    } else {',start)
    text+='if(D_8037C279){\n'+src[start:end]+'\n}\n}\n'
    text+=r'''
void ground_ref_vertex(unsigned role,unsigned vertex,const int16_t*xyz){
 BKVertexList*v=role?mapModel.model_bin_xlu:mapModel.model_bin_opa;memcpy(v->vertices[vertex].v.ob,xyz,6);
}
'''
    tmp=tempfile.TemporaryDirectory(prefix='ground-original-');p=Path(tmp.name);(p/'ref.c').write_text(text)
    subprocess.run(['cc',*FLAGS,opt,'-shared','-fPIC',str(p/'ref.c'),'-lm','-o',str(p/'ref.so')],check=True)
    lib=C.CDLL(str(p/'ref.so'));lib._tmp=tmp
    lib.ref_load.argtypes=[C.c_int,C.c_void_p];lib.floor_ref_step.argtypes=[C.POINTER(F),F,C.c_uint32,C.c_uint]
    lib.floor_ref_snapshot.argtypes=[C.c_void_p];lib.ground_ref_vertex.argtypes=[C.c_uint,C.c_uint,C.c_void_p]
    return lib
