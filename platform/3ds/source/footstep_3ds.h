#ifndef BANJO_FOOTSTEP_3DS_H
#define BANJO_FOOTSTEP_3DS_H

#include "footstep.h"

/* Walking footsteps on NDSP channels 1 and 2. Channel 0 stays the crouch
 * slide. Init after sfxProbe3dsInit, submit after sfxProbe3dsFrame, and exit
 * before sfxProbe3dsExit. This file does not call ndspInit or ndspExit.
 * A missing sample or a down DSP leaves that step silent. */
void footstep3dsInit(void);
void footstep3dsSubmit(const BanjoFootPlay *plays, int count);
void footstep3dsExit(void);

#endif
