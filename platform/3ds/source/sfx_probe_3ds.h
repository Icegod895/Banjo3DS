#ifndef BANJO_SFX_PROBE_3DS_H
#define BANJO_SFX_PROBE_3DS_H

#include <stdbool.h>

/* Slide voice. Call init once after the scene exists, frame once after each
 * presented frame, and exit on every shutdown path that reached init.
 * sustain is 1 while this frame's crouch coast raised sfx_count. The voice
 * stays silent until the first 1, loops SFX_18 across sustained frames, and
 * plays SFX_19 once on the first 0. A missing PCM asset or a failed ndspInit
 * leaves the rest of the frame alone. */
void sfxProbe3dsInit(void);
void sfxProbe3dsFrame(int sustain);
void sfxProbe3dsExit(void);
/* Read-only. The slide voice still owns ndspInit and ndspExit. */
int sfxProbe3dsReady(void);
/* One-shot original Bottles emergence SFX_C6 on owner-only NDSP channel 4.
 * Silent when NDSP or this extracted sample is unavailable. */
void sfxProbe3dsBottlesEmergence(void);
/* Original state-2 animation thresholds .40 (SFX_2C) and .75 (SFX_C5).
 * Share the owner-managed one-shot channel 4 without preempting C6. */
void sfxProbe3dsBottlesPull(void);
void sfxProbe3dsBottlesPop(void);
/* Original SFX_3F9 retreat loop: returns false if audio/sample/channel is not
 * available. Repeated starts are idempotent; stop and shutdown release it. */
bool sfxProbe3dsBottlesRetreatStart(void);
void sfxProbe3dsBottlesRetreatStop(void);
/* Original state-2 SFX_3F9 source, independent of channel-4 one-shots. */
bool sfxProbe3dsBottlesEmergenceLoopStart(void);
void sfxProbe3dsBottlesEmergenceLoopStop(void);

#endif
