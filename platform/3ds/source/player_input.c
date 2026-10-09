#include "player_input.h"
#include <3ds/types.h>
#include <3ds/services/hid.h>
#include "../../../tools/banjo3ds/camera_manual/manual.h"
_Static_assert((int)PI_N64_R==(int)BM_R && (int)PI_N64_CLEFT==(int)BM_LEFT
    && (int)PI_N64_CRIGHT==(int)BM_RIGHT && (int)PI_N64_CDOWN==(int)BM_DOWN,
    "Logical manual buttons must match the proven controller");
static int8_t axis(int value,int8_t previous) {
    if(value>=PI_CSTICK_PRESS)return 1;
    if(value<=-PI_CSTICK_PRESS)return -1;
    if(previous>0 && value>PI_CSTICK_RELEASE)return 1;
    if(previous<0 && value<-PI_CSTICK_RELEASE)return -1;
    return 0;
}
PlayerInputFrame playerInputUpdate(PlayerInputState *s,uint32_t keys,int16_t x,int16_t y) {
    PlayerInputFrame out={0};
    const uint32_t faces=keys&(KEY_A|KEY_B|KEY_X|KEY_Y);
    const bool modifier=(keys&KEY_R)!=0;
    /* A face used in a chord must not become jump/R/Y on modifier release.
     * Pressing the modifier around an already-held face still forms a chord. */
    s->consumed_faces&=faces;
    if(modifier)s->consumed_faces|=faces;
    uint32_t ordinary=faces&~s->consumed_faces;
    s->cstick_x=axis(x,s->cstick_x);s->cstick_y=axis(y,s->cstick_y);
    if((keys&KEY_DLEFT) || s->cstick_x<0 || (modifier && (faces&KEY_Y)))out.held|=PI_N64_CLEFT;
    if((keys&KEY_DRIGHT) || s->cstick_x>0 || (modifier && (faces&KEY_A)))out.held|=PI_N64_CRIGHT;
    if((keys&KEY_DUP) || s->cstick_y>0 || (modifier && (faces&KEY_X)))out.held|=PI_N64_CUP;
    if((keys&KEY_DDOWN) || s->cstick_y<0 || (modifier && (faces&KEY_B)))out.held|=PI_N64_CDOWN;
    if(ordinary&KEY_X)out.held|=PI_N64_R;
    if(ordinary&KEY_A)out.held|=PI_N64_A;
    if(ordinary&KEY_B)out.held|=PI_N64_B;
    if(keys&KEY_L)out.held|=PI_N64_Z;
    if(keys&KEY_START)out.held|=PI_START;
    out.pressed=out.held&~s->held;out.released=s->held&~out.held;
    out.manual=out.held&(BM_R|BM_LEFT|BM_RIGHT|BM_DOWN);
    out.jump_pressed=(out.pressed&PI_N64_A)!=0;
    out.suppress_movement=(ordinary&KEY_Y)!=0;
    s->held=out.held;
    return out;
}
