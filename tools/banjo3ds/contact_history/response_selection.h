#ifndef BANJO_RESPONSE_SELECTION_H
#define BANJO_RESPONSE_SELECTION_H
#include <stdint.h>
#include <math.h>
/* Source: playerutils player_isActive and code_15F20 func_8029CED0.
 * BA_FLAG_3/4 are byte-array indices, represented here as known booleans.
 * This low-level selector accepts a previously classified category and floor
 * flags; it does not authenticate history or advance any observation. */
typedef struct {
    uint32_t immune3, immune4;
    uint32_t override_enabled[4];
    float override_value[4];
} ChResponseEngine;
typedef struct { uint32_t active; float coefficient; } ChResponseSelection;
/* Internal shared policy, immutable non-aliasing inputs and local output.
 * Disabled finite negative values are allowed, as in the original observer;
 * every enabled value must be finite/nonnegative. No implicit defaults for
 * unknown booleans or categories. Output unchanged on rejection. */
static inline int ch_select_response(uint32_t category, uint32_t floor_flags,
    const ChResponseEngine *e, ChResponseSelection *out) {
    if(!e || !out || category<1 || category>4 || e->immune3>1 || e->immune4>1)
        return 0;
    for(int i=0;i<4;i++)if(e->override_enabled[i]>1 ||
        !isfinite(e->override_value[i]) ||
        (e->override_enabled[i] && e->override_value[i]<0))return 0;
    static const float defaults[4]={.07f,.29f,.15f,.05f};
    unsigned c=category-1;
    ChResponseSelection n;
    n.coefficient=e->override_enabled[c] ? e->override_value[c] : defaults[c];
    n.active=((floor_flags&0x10) && !e->immune3) ||
             ((floor_flags&0x40) && !e->immune4);
    *out=n;return 1;
}
#endif
