#include <3ds.h>
#include <stdint.h>
#include <string.h>

#include "generated_sfx_probe.h"
#include "sfx_probe_3ds.h"
#include "sfx_voice.h"

/* One NDSP channel. A verified SFX_18 loop queues the intro once, then
 * repeats the [start, end) body while sustain stays set. The first frame
 * with sustain clear hard-cuts that voice and queues SFX_19. PCM stays
 * allocated until exit so a later coast can start on the same pitch walk.
 * NDSP cannot loop a subrange, and the generator sets LOOP_VERIFIED only
 * when the bank ADPCM state matches that linear frame. An unverified slide
 * plays the whole buffer once and waits out a finished buffer before the
 * closer. The 3200 us Rare release ramp is not applied. Pitch steps once
 * per sustained frame inside the voice, not on a claimed N64 tick. */

_Static_assert(BANJO_SFX19_PCM_BYTES == 0 || (BANJO_SFX19_PCM_BYTES % 2) == 0,
    "SFX_19 probe PCM is whole 16-bit samples");
_Static_assert(BANJO_SFX18_INTRO_PCM_BYTES == 0 || (BANJO_SFX18_INTRO_PCM_BYTES % 2) == 0,
    "SFX_18 intro PCM is whole 16-bit samples");
_Static_assert(BANJO_SFX18_LOOP_PCM_BYTES == 0 || (BANJO_SFX18_LOOP_PCM_BYTES % 2) == 0,
    "SFX_18 loop PCM is whole 16-bit samples");
_Static_assert(BANJO_SFX18_ONCE_PCM_BYTES == 0 || (BANJO_SFX18_ONCE_PCM_BYTES % 2) == 0,
    "SFX_18 one-shot PCM is whole 16-bit samples");
_Static_assert(BANJO_SFX19_INDEX == 0x19, "SFX_19 selects soundArray index 0x19");
_Static_assert(BANJO_SFX18_INDEX == 0x18, "SFX_18 selects soundArray index 0x18");
_Static_assert(SFX_PROBE_RATE == 22000, "playback uses the N64 AI rate");
_Static_assert(SFX_PROBE_RATE == BANJO_SFX_PROBE_RATE_HZ, "generated probe rate drifted");
_Static_assert(SFX_PROBE_SLIDE_MS == 2000, "the slide hold is 2000 ms");
_Static_assert(SFX_PROBE_SLIDE_MS == BANJO_SFX_PROBE_SLIDE_MS, "generated slide hold drifted");
_Static_assert(SFX_SLIDE_SOURCE_VOLUME == 28000, "SFX_18 source loudness");
_Static_assert(SFX_CLOSER_SOURCE_VOLUME == 22000, "SFX_19 source loudness");
_Static_assert(BANJO_SFX18_LOOP_VERIFIED == 0 || BANJO_SFX18_LOOP_VERIFIED == 1,
    "loop verification is a flag");

static SfxVoice voice;
static ndspWaveBuf intro_wave;
static ndspWaveBuf loop_wave;
static ndspWaveBuf once_wave;
static ndspWaveBuf closer_wave;
static s16 *intro_pcm;
static s16 *loop_pcm;
static s16 *once_pcm;
static s16 *closer_pcm;
static u32 intro_samples;
static u32 loop_samples;
static u32 once_samples;
static u32 closer_samples;
static int slide_queued;
static int channel_queued;
static int ndsp_up;

static void free_pcm(s16 **pcm)
{
    if (!pcm || !*pcm)
        return;
    linearFree(*pcm);
    *pcm = NULL;
}

static void free_all_pcm(void)
{
    free_pcm(&intro_pcm);
    free_pcm(&loop_pcm);
    free_pcm(&once_pcm);
    free_pcm(&closer_pcm);
    intro_samples = 0;
    loop_samples = 0;
    once_samples = 0;
    closer_samples = 0;
}

static s16 *stage_pcm(const unsigned char *src, u32 bytes)
{
    s16 *buffer;
    u32 flush_size;

    if (bytes < 2 || (bytes % 2) != 0)
        return NULL;
    buffer = linearAlloc(bytes);
    if (!buffer || ((uintptr_t)buffer & 0x7f) != 0) {
        if (buffer)
            linearFree(buffer);
        return NULL;
    }
    memcpy(buffer, src, bytes);
    flush_size = bytes;
    if (linearGetSize(buffer) >= bytes)
        flush_size = (u32)linearGetSize(buffer);
    if (flush_size == 0 || R_FAILED(DSP_FlushDataCache(buffer, flush_size))) {
        linearFree(buffer);
        return NULL;
    }
    return buffer;
}

static float voice_level(int known, int attack, int sample, int source)
{
    int volume;

    if (!known)
        return 1.0f;
    volume = sfxSynthVolume(SFX_LEVEL_TABLE, attack, source, sample);
    return (float)volume / 32767.0f;
}

static void configure_channel(float rate, float level)
{
    float mix[12];
    int channel;

    ndspChnSetInterp(0, NDSP_INTERP_LINEAR);
    ndspChnSetFormat(0, NDSP_FORMAT_MONO_PCM16);
    ndspChnSetRate(0, rate);
    for (channel = 0; channel < 12; channel++)
        mix[channel] = 0.0f;
    mix[0] = level;
    mix[1] = level;
    ndspChnSetMix(0, mix);
}

static void clear_channel(void)
{
    if (channel_queued)
        ndspChnWaveBufClear(0);
    channel_queued = 0;
    slide_queued = 0;
    memset(&intro_wave, 0, sizeof(intro_wave));
    memset(&loop_wave, 0, sizeof(loop_wave));
    memset(&once_wave, 0, sizeof(once_wave));
    memset(&closer_wave, 0, sizeof(closer_wave));
}

static void queue_slide(void)
{
    float level = voice_level(BANJO_SFX18_VOLUME_KNOWN, BANJO_SFX18_ATTACK_VOLUME,
        BANJO_SFX18_SAMPLE_VOLUME, SFX_SLIDE_SOURCE_VOLUME);

    configure_channel(sfxVoiceRate(&voice), level);
    if (voice.slide_ready == SFX_SLIDE_LOOP && loop_pcm) {
        if (intro_pcm) {
            memset(&intro_wave, 0, sizeof(intro_wave));
            intro_wave.data_pcm16 = intro_pcm;
            intro_wave.nsamples = intro_samples;
            intro_wave.looping = false;
            intro_wave.status = NDSP_WBUF_FREE;
            ndspChnWaveBufAdd(0, &intro_wave);
        }
        memset(&loop_wave, 0, sizeof(loop_wave));
        loop_wave.data_pcm16 = loop_pcm;
        loop_wave.nsamples = loop_samples;
        loop_wave.looping = true;
        loop_wave.status = NDSP_WBUF_FREE;
        ndspChnWaveBufAdd(0, &loop_wave);
        slide_queued = 1;
        channel_queued = 1;
        return;
    }
    if (voice.slide_ready == SFX_SLIDE_ONCE && once_pcm) {
        memset(&once_wave, 0, sizeof(once_wave));
        once_wave.data_pcm16 = once_pcm;
        once_wave.nsamples = once_samples;
        once_wave.looping = false;
        once_wave.status = NDSP_WBUF_FREE;
        ndspChnWaveBufAdd(0, &once_wave);
        slide_queued = 1;
        channel_queued = 1;
    }
}

static void queue_closer(void)
{
    float level = voice_level(BANJO_SFX19_VOLUME_KNOWN, BANJO_SFX19_ATTACK_VOLUME,
        BANJO_SFX19_SAMPLE_VOLUME, SFX_CLOSER_SOURCE_VOLUME);

    if (!closer_pcm)
        return;
    configure_channel(sfxVoiceRate(&voice), level);
    memset(&closer_wave, 0, sizeof(closer_wave));
    closer_wave.data_pcm16 = closer_pcm;
    closer_wave.nsamples = closer_samples;
    closer_wave.looping = false;
    closer_wave.status = NDSP_WBUF_FREE;
    ndspChnWaveBufAdd(0, &closer_wave);
    channel_queued = 1;
}

static void finish_closer(void)
{
    if (voice.phase != SFX_VOICE_CLOSER || !closer_pcm || closer_wave.status != NDSP_WBUF_DONE)
        return;
    clear_channel();
    sfxVoiceComplete(&voice);
}

void sfxProbe3dsInit(void)
{
    int mode = SFX_SLIDE_NONE;
    int closer_ready = 0;
    int ndsp_ready = 0;

    sfxVoiceReset(&voice);
    /* Keep every generated buffer referenced for both header shapes. */
    (void)banjo_sfx19_pcm[0];
    (void)banjo_sfx18_intro_pcm[0];
    (void)banjo_sfx18_loop_pcm[0];
    (void)banjo_sfx18_once_pcm[0];
    intro_pcm = NULL;
    loop_pcm = NULL;
    once_pcm = NULL;
    closer_pcm = NULL;
    intro_samples = 0;
    loop_samples = 0;
    once_samples = 0;
    closer_samples = 0;
    slide_queued = 0;
    channel_queued = 0;
    ndsp_up = 0;
    memset(&intro_wave, 0, sizeof(intro_wave));
    memset(&loop_wave, 0, sizeof(loop_wave));
    memset(&once_wave, 0, sizeof(once_wave));
    memset(&closer_wave, 0, sizeof(closer_wave));

    if (BANJO_SFX18_LOOP_VERIFIED && BANJO_SFX18_LOOP_PCM_BYTES >= 2)
        mode = SFX_SLIDE_LOOP;
    else if (!BANJO_SFX18_LOOP_VERIFIED && BANJO_SFX18_ONCE_PCM_BYTES >= 2)
        mode = SFX_SLIDE_ONCE;

    if (mode != SFX_SLIDE_NONE && R_SUCCEEDED(ndspInit())) {
        ndsp_up = 1;
        ndspSetOutputMode(NDSP_OUTPUT_STEREO);
        ndspSetMasterVol(1.0f);
        ndspChnReset(0);
        configure_channel((float)SFX_PROBE_RATE, 0.0f);
        if (mode == SFX_SLIDE_LOOP) {
            if (BANJO_SFX18_INTRO_PCM_BYTES >= 2) {
                intro_pcm = stage_pcm(banjo_sfx18_intro_pcm, BANJO_SFX18_INTRO_PCM_BYTES);
                if (!intro_pcm)
                    mode = SFX_SLIDE_NONE;
                else
                    intro_samples = BANJO_SFX18_INTRO_PCM_BYTES / sizeof(s16);
            }
            if (mode == SFX_SLIDE_LOOP) {
                loop_pcm = stage_pcm(banjo_sfx18_loop_pcm, BANJO_SFX18_LOOP_PCM_BYTES);
                if (!loop_pcm)
                    mode = SFX_SLIDE_NONE;
                else
                    loop_samples = BANJO_SFX18_LOOP_PCM_BYTES / sizeof(s16);
            }
        } else {
            once_pcm = stage_pcm(banjo_sfx18_once_pcm, BANJO_SFX18_ONCE_PCM_BYTES);
            if (!once_pcm)
                mode = SFX_SLIDE_NONE;
            else
                once_samples = BANJO_SFX18_ONCE_PCM_BYTES / sizeof(s16);
        }
        if (mode != SFX_SLIDE_NONE && BANJO_SFX19_PCM_BYTES >= 2) {
            closer_pcm = stage_pcm(banjo_sfx19_pcm, BANJO_SFX19_PCM_BYTES);
            if (closer_pcm) {
                closer_samples = BANJO_SFX19_PCM_BYTES / sizeof(s16);
                closer_ready = 1;
            }
        }
        if (mode == SFX_SLIDE_NONE) {
            free_all_pcm();
            closer_ready = 0;
        } else {
            ndsp_ready = 1;
        }
    }
    if (!ndsp_ready)
        mode = SFX_SLIDE_NONE;
    sfxVoiceBind(&voice, ndsp_ready, mode, closer_ready, SFX_PROBE_RATE, SFX_PROBE_SLIDE_MS);
}

void sfxProbe3dsFrame(int sustain)
{
    int action;
    int once_done;

    if (!voice.armed || !ndsp_up)
        return;
    once_done = voice.phase == SFX_VOICE_SLIDE && voice.slide_ready == SFX_SLIDE_ONCE
        && slide_queued && once_wave.status == NDSP_WBUF_DONE;
    if (once_done && sustain)
        action = 0;
    else if (once_done)
        action = sfxVoiceSlideFinished(&voice, 0);
    else
        action = sfxVoiceSustain(&voice, sustain);
    if (action & SFX_VOICE_STOP_SLIDE)
        clear_channel();
    if (action & SFX_VOICE_QUEUE_SLIDE)
        queue_slide();
    if (action & SFX_VOICE_QUEUE_CLOSER)
        queue_closer();
    else if (action & SFX_VOICE_SET_RATE)
        ndspChnSetRate(0, sfxVoiceRate(&voice));
    if (!sustain)
        finish_closer();
}

int sfxProbe3dsReady(void)
{
    return ndsp_up;
}

void sfxProbe3dsExit(void)
{
    int held = sfxVoiceShutdown(&voice);

    if ((held == 1 || held == 2) && ndsp_up)
        ndspChnWaveBufClear(0);
    free_all_pcm();
    memset(&intro_wave, 0, sizeof(intro_wave));
    memset(&loop_wave, 0, sizeof(loop_wave));
    memset(&once_wave, 0, sizeof(once_wave));
    memset(&closer_wave, 0, sizeof(closer_wave));
    slide_queued = 0;
    channel_queued = 0;
    if (ndsp_up) {
        ndspExit();
        ndsp_up = 0;
    }
}
