#include "sfx_voice.h"

static float pitch_unit(unsigned *rng)
{
    unsigned x = *rng;

    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    if (x == 0)
        x = SFX_PITCH_RNG_SEED;
    *rng = x;
    return (float)(x >> 8) * (1.0f / 16777216.0f);
}

static int begin_closer(SfxVoice *voice)
{
    if (voice->closer_ready) {
        voice->phase = SFX_VOICE_CLOSER;
        voice->queue_closer_count += 1;
        return SFX_VOICE_STOP_SLIDE | SFX_VOICE_QUEUE_CLOSER | SFX_VOICE_SET_RATE;
    }
    voice->phase = SFX_VOICE_DONE;
    return SFX_VOICE_STOP_SLIDE;
}

static int begin_slide(SfxVoice *voice, int stop_current)
{
    int action;

    voice->pitch = sfxSlidePitchStep(voice->pitch, pitch_unit(&voice->rng));
    voice->pitch_steps += 1;
    voice->phase = SFX_VOICE_SLIDE;
    voice->queue_slide_count += 1;
    action = SFX_VOICE_QUEUE_SLIDE | SFX_VOICE_SET_RATE;
    if (stop_current)
        action |= SFX_VOICE_STOP_SLIDE;
    return action;
}

void sfxVoiceReset(SfxVoice *voice)
{
    if (!voice)
        return;
    voice->ndsp_ready = 0;
    voice->slide_ready = SFX_SLIDE_NONE;
    voice->closer_ready = 0;
    voice->sample_rate = 0;
    voice->slide_ms = 0;
    voice->phase = SFX_VOICE_IDLE;
    voice->armed = 0;
    voice->started_ms = 0;
    voice->pitch_steps = 0;
    voice->queue_slide_count = 0;
    voice->queue_closer_count = 0;
    voice->release_count = 0;
    voice->rng = SFX_PITCH_RNG_SEED;
    voice->pitch = 1.0f;
}

int sfxSynthVolume(int table, int envelope, int source, int sample_volume)
{
    int inner;
    int scaled;

    if (table < 0 || envelope < 0 || source < 0 || sample_volume < 0)
        return 0;
    inner = (envelope * source * sample_volume) / 16129;
    scaled = (table * inner) / 32767 - 1;
    if (scaled < 0)
        return 0;
    if (scaled > 32767)
        return 32767;
    return scaled;
}

float sfxSlidePitchMin(void)
{
    return 0.9f;
}

float sfxSlidePitchMax(void)
{
    return 1.5f;
}

float sfxSlidePitchStep(float pitch, float unit)
{
    if (unit < 0.0f)
        unit = 0.0f;
    if (unit >= 1.0f)
        unit = 0.99999994f;
    pitch += unit * 0.1f - 0.05f;
    if (pitch < 0.9f)
        pitch = 0.9f;
    if (pitch > 1.5f)
        pitch = 1.5f;
    return pitch;
}

int sfxVoiceBind(SfxVoice *voice, int ndsp_ready, int slide_ready, int closer_ready,
    int sample_rate, int slide_ms)
{
    int slide_ok;

    if (!voice || voice->phase != SFX_VOICE_IDLE || voice->armed)
        return 0;
    voice->ndsp_ready = ndsp_ready;
    voice->closer_ready = closer_ready ? 1 : 0;
    voice->sample_rate = sample_rate;
    voice->slide_ms = slide_ms;
    slide_ok = slide_ready == SFX_SLIDE_LOOP || slide_ready == SFX_SLIDE_ONCE;
    if (!ndsp_ready || sample_rate != SFX_PROBE_RATE || slide_ms <= 0 || !slide_ok) {
        voice->phase = SFX_VOICE_SKIPPED;
        voice->slide_ready = SFX_SLIDE_NONE;
        return 0;
    }
    voice->slide_ready = slide_ready;
    voice->armed = 1;
    voice->pitch = 1.0f;
    voice->rng = SFX_PITCH_RNG_SEED;
    return 1;
}

int sfxVoicePoll(SfxVoice *voice, int now_ms)
{
    if (!voice || !voice->armed)
        return 0;
    if (voice->phase == SFX_VOICE_IDLE) {
        voice->pitch = sfxSlidePitchStep(voice->pitch, pitch_unit(&voice->rng));
        voice->pitch_steps = 1;
        voice->phase = SFX_VOICE_SLIDE;
        voice->started_ms = now_ms;
        voice->queue_slide_count = 1;
        return SFX_VOICE_QUEUE_SLIDE | SFX_VOICE_SET_RATE;
    }
    if (voice->phase == SFX_VOICE_SLIDE) {
        if ((unsigned)now_ms - (unsigned)voice->started_ms >= (unsigned)voice->slide_ms)
            return begin_closer(voice);
        voice->pitch = sfxSlidePitchStep(voice->pitch, pitch_unit(&voice->rng));
        voice->pitch_steps += 1;
        return SFX_VOICE_SET_RATE;
    }
    return 0;
}

int sfxVoiceSustain(SfxVoice *voice, int sustain)
{
    if (!voice || !voice->armed || voice->phase == SFX_VOICE_SKIPPED)
        return 0;
    if (voice->phase == SFX_VOICE_CLOSER) {
        if (!sustain)
            return 0;
        return begin_slide(voice, 1);
    }
    if (voice->phase == SFX_VOICE_SLIDE) {
        if (!sustain)
            return begin_closer(voice);
        voice->pitch = sfxSlidePitchStep(voice->pitch, pitch_unit(&voice->rng));
        voice->pitch_steps += 1;
        return SFX_VOICE_SET_RATE;
    }
    if (!sustain)
        return 0;
    if (voice->phase == SFX_VOICE_IDLE || voice->phase == SFX_VOICE_DONE)
        return begin_slide(voice, 0);
    return 0;
}

int sfxVoiceSlideFinished(SfxVoice *voice, int now_ms)
{
    (void)now_ms;
    if (!voice || voice->phase != SFX_VOICE_SLIDE || voice->slide_ready != SFX_SLIDE_ONCE)
        return 0;
    return begin_closer(voice);
}

void sfxVoiceComplete(SfxVoice *voice)
{
    if (!voice || voice->phase != SFX_VOICE_CLOSER)
        return;
    voice->phase = SFX_VOICE_DONE;
}

int sfxVoiceShutdown(SfxVoice *voice)
{
    if (!voice)
        return 0;
    if (voice->phase == SFX_VOICE_SLIDE) {
        voice->phase = SFX_VOICE_DONE;
        voice->armed = 0;
        voice->release_count += 1;
        return 1;
    }
    if (voice->phase == SFX_VOICE_CLOSER) {
        voice->phase = SFX_VOICE_DONE;
        voice->armed = 0;
        voice->release_count += 1;
        return 2;
    }
    if (voice->phase == SFX_VOICE_IDLE && voice->armed) {
        voice->phase = SFX_VOICE_DONE;
        voice->armed = 0;
    }
    return 0;
}

float sfxVoicePitch(const SfxVoice *voice)
{
    if (!voice)
        return 1.0f;
    return voice->pitch;
}

float sfxVoiceRate(const SfxVoice *voice)
{
    if (!voice)
        return 0.0f;
    return (float)voice->sample_rate * voice->pitch;
}
