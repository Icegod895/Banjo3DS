#ifndef BANJO_SFX_VOICE_H
#define BANJO_SFX_VOICE_H

#include "sfx_probe.h"

/* One NDSP voice. The slide bed and the SFX_19 closer never overlap:
 * QUEUE_CLOSER is only returned together with STOP_SLIDE, on the same channel.
 * Pitch follows basfx_80299AAC: add unit*0.1 - 0.05 and clamp to [0.9, 1.5].
 * unit is in [0, 1), matching randf(). The live game seed is not known here,
 * so the voice draws unit from a fixed xorshift instead of claiming a retail
 * sequence. The step and the clamp are the original formula.
 * sfxVoiceSustain is the gameplay lifecycle. sfxVoicePoll still ends a slide
 * after slide_ms and is not the crouch stop. */

#define SFX_SLIDE_NONE 0
#define SFX_SLIDE_LOOP 1
#define SFX_SLIDE_ONCE 2

#define SFX_VOICE_IDLE 0
#define SFX_VOICE_SLIDE 1
#define SFX_VOICE_CLOSER 2
#define SFX_VOICE_DONE 3
#define SFX_VOICE_SKIPPED 4

#define SFX_VOICE_QUEUE_SLIDE 1
#define SFX_VOICE_SET_RATE 2
#define SFX_VOICE_STOP_SLIDE 4
#define SFX_VOICE_QUEUE_CLOSER 8

#define SFX_PITCH_RNG_SEED 0x4D343133u

typedef struct SfxVoice {
    int ndsp_ready;
    int slide_ready;
    int closer_ready;
    int sample_rate;
    int slide_ms;
    int phase;
    int armed;
    int started_ms;
    int pitch_steps;
    int queue_slide_count;
    int queue_closer_count;
    int release_count;
    unsigned rng;
    float pitch;
} SfxVoice;

void sfxVoiceReset(SfxVoice *voice);
int sfxSynthVolume(int table, int envelope, int source, int sample_volume);
float sfxSlidePitchMin(void);
float sfxSlidePitchMax(void);
float sfxSlidePitchStep(float pitch, float unit);
int sfxVoiceBind(SfxVoice *voice, int ndsp_ready, int slide_ready, int closer_ready,
    int sample_rate, int slide_ms);
int sfxVoicePoll(SfxVoice *voice, int now_ms);
/* sustain is 1 on a frame that raised the crouch sfx_count. Pitch continues
 * across coasts. A sustain during the closer cuts that one-shot and queues
 * the slide again. Shutdown disarms the voice so a later sustain stays silent. */
int sfxVoiceSustain(SfxVoice *voice, int sustain);
int sfxVoiceSlideFinished(SfxVoice *voice, int now_ms);
void sfxVoiceComplete(SfxVoice *voice);
int sfxVoiceShutdown(SfxVoice *voice);
float sfxVoicePitch(const SfxVoice *voice);
float sfxVoiceRate(const SfxVoice *voice);

#endif
