#include <3ds.h>
#include <stdint.h>
#include <string.h>

#include "generated_sfx_probe.h"
#include "sfx_probe.h"
#include "sfx_probe_3ds.h"

_Static_assert(BANJO_SFX19_PCM_BYTES == 0 || (BANJO_SFX19_PCM_BYTES % 2) == 0,
    "SFX_19 probe PCM is whole 16-bit samples");
_Static_assert(BANJO_SFX18_PCM_BYTES == 0 || (BANJO_SFX18_PCM_BYTES % 2) == 0,
    "SFX_18 probe PCM is whole 16-bit samples");
_Static_assert(BANJO_SFX19_INDEX == 0x19, "SFX_19 selects soundArray index 0x19");
_Static_assert(BANJO_SFX18_INDEX == 0x18, "SFX_18 selects soundArray index 0x18");
_Static_assert(SFX_PROBE_RATE == 22000, "both clips play the wavetable at the N64 AI rate");
_Static_assert(SFX_PROBE_RATE == BANJO_SFX_PROBE_RATE_HZ, "generated probe rate drifted");
_Static_assert(SFX_PROBE_GAP_MS == 400, "listening gap is 400 ms");
_Static_assert(SFX_PROBE_GAP_MS == BANJO_SFX_PROBE_GAP_MS, "generated probe gap drifted");

static SfxProbe probe;
static ndspWaveBuf wave;
static s16 *linear_pcm;
static int ndsp_up;

static void release_buffer(void)
{
    if (!linear_pcm)
        return;
    ndspChnWaveBufClear(0);
    linearFree(linear_pcm);
    linear_pcm = NULL;
    memset(&wave, 0, sizeof(wave));
}

static void fail_clip(int now_ms)
{
    if (linear_pcm) {
        linearFree(linear_pcm);
        linear_pcm = NULL;
    }
    sfxProbeComplete(&probe, now_ms);
}

static void queue_clip(int now_ms)
{
    u32 bytes = probe.clip == SFX_PROBE_CLIP_SLIDE
        ? (u32)probe.slide_bytes : (u32)probe.landing_bytes;
    const unsigned char *pcm = probe.clip == SFX_PROBE_CLIP_SLIDE
        ? banjo_sfx18_pcm : banjo_sfx19_pcm;
    u32 flush_size;

    if (bytes < 2 || (bytes % 2) != 0) {
        fail_clip(now_ms);
        return;
    }
    linear_pcm = linearAlloc(bytes);
    if (!linear_pcm || ((uintptr_t)linear_pcm & 0x7f) != 0) {
        fail_clip(now_ms);
        return;
    }
    memcpy(linear_pcm, pcm, bytes);
    flush_size = bytes;
    if (linearGetSize(linear_pcm) >= bytes)
        flush_size = (u32)linearGetSize(linear_pcm);
    if (R_FAILED(DSP_FlushDataCache(linear_pcm, flush_size))) {
        fail_clip(now_ms);
        return;
    }
    memset(&wave, 0, sizeof(wave));
    wave.data_pcm16 = linear_pcm;
    wave.nsamples = bytes / sizeof(s16);
    wave.looping = false;
    wave.status = NDSP_WBUF_FREE;
    ndspChnWaveBufAdd(0, &wave);
}

void sfxProbe3dsInit(void)
{
    int ready = 0;

    sfxProbeReset(&probe);
    linear_pcm = NULL;
    ndsp_up = 0;
    memset(&wave, 0, sizeof(wave));
    if (BANJO_SFX19_PCM_BYTES >= 2 || BANJO_SFX18_PCM_BYTES >= 2) {
        if (R_SUCCEEDED(ndspInit())) {
            ndsp_up = 1;
            ndspSetOutputMode(NDSP_OUTPUT_STEREO);
            ndspSetMasterVol(1.0f);
            ndspChnReset(0);
            ndspChnSetInterp(0, NDSP_INTERP_LINEAR);
            ndspChnSetFormat(0, NDSP_FORMAT_MONO_PCM16);
            ndspChnSetRate(0, (float)SFX_PROBE_RATE);
            {
                float mix[12];
                int channel;
                for (channel = 0; channel < 12; channel++)
                    mix[channel] = 0.0f;
                mix[0] = 1.0f;
                mix[1] = 1.0f;
                ndspChnSetMix(0, mix);
            }
            ready = 1;
        }
    }
    sfxProbeBind(&probe, ready,
        (int)BANJO_SFX19_PCM_BYTES, (int)BANJO_SFX18_PCM_BYTES, SFX_PROBE_RATE);
}

void sfxProbe3dsFrame(void)
{
    /* osGetTime is milliseconds since 1900. The low 32 bits are enough for
     * the 400 ms gap; sfxProbePoll subtracts them unsigned. */
    int now_ms = (int)osGetTime();

    if (sfxProbePoll(&probe, now_ms)) {
        queue_clip(now_ms);
        return;
    }
    if (probe.phase == SFX_PROBE_QUEUED && linear_pcm && wave.status == NDSP_WBUF_DONE) {
        release_buffer();
        sfxProbeComplete(&probe, now_ms);
    }
}

void sfxProbe3dsExit(void)
{
    if (sfxProbeShutdown(&probe))
        release_buffer();
    if (ndsp_up) {
        ndspExit();
        ndsp_up = 0;
    }
}
