#ifndef BANJO_SFX_PROBE_3DS_H
#define BANJO_SFX_PROBE_3DS_H

/* Slide voice. Call init once after the scene exists, frame once after each
 * presented frame, and exit on every shutdown path that reached init.
 * sustain is 1 while this frame's crouch coast raised sfx_count. The voice
 * stays silent until the first 1, loops SFX_18 across sustained frames, and
 * plays SFX_19 once on the first 0. A missing PCM asset or a failed ndspInit
 * leaves the rest of the frame alone. */
void sfxProbe3dsInit(void);
void sfxProbe3dsFrame(int sustain);
void sfxProbe3dsExit(void);

#endif
