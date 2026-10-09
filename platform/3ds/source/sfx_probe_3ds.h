#ifndef BANJO_SFX_PROBE_3DS_H
#define BANJO_SFX_PROBE_3DS_H

/* Listening probe. Call init once after the scene exists, frame once after
 * each presented frame, and exit on every shutdown path that reached init.
 * After the first presented frame this plays SFX_19 once, waits 400 ms, then
 * plays unlooped SFX_18 once. A missing PCM asset or a failed ndspInit leaves
 * the rest of the frame alone. */
void sfxProbe3dsInit(void);
void sfxProbe3dsFrame(void);
void sfxProbe3dsExit(void);

#endif
