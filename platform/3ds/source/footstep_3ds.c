#include <3ds.h>
#include <stdint.h>
#include <string.h>

#include "footstep_3ds.h"
#include "generated_sfx_foot.h"
#include "sfx_probe.h"
#include "sfx_probe_3ds.h"
#include "sfx_voice.h"

/* Two one-shot voices, matching unk1C and unk1D. A new step on a source
 * clears that source's channel and starts again. The other source keeps
 * playing. Channel 0 is never addressed. Playback rate is the AI clock times
 * the varied pitch times alCents2Ratio(keyBase), which is unk2C * unk28.
 * The table integer is loudness through sfxSynthVolume. Attack time on these
 * notes is 0, so the level is the attack volume for the whole one-shot. */

_Static_assert(BANJO_FOOT_AI_RATE == 22000, "footsteps use the N64 AI clock");
_Static_assert(SFX_PROBE_RATE == 22000, "the slide clock and the foot clock match");
_Static_assert(BANJO_FOOT_PCM_COUNT > 0, "the footstep table has a slot");

static s16 *pcm_buffers[BANJO_FOOT_PCM_COUNT];
static u32 pcm_samples[BANJO_FOOT_PCM_COUNT];
static ndspWaveBuf waves[2];
static int staged;

static void free_pcm(s16 **pcm)
{
    if (!pcm || !*pcm)
        return;
    linearFree(*pcm);
    *pcm = NULL;
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

static int channel_for_source(int source)
{
    if (source == 0)
        return 1;
    if (source == 1)
        return 2;
    return -1;
}

static void configure_channel(int channel, float rate, float level)
{
    float mix[12];
    int speaker;

    ndspChnSetInterp(channel, NDSP_INTERP_LINEAR);
    ndspChnSetFormat(channel, NDSP_FORMAT_MONO_PCM16);
    ndspChnSetRate(channel, rate);
    for (speaker = 0; speaker < 12; speaker++)
        mix[speaker] = 0.0f;
    mix[0] = level;
    mix[1] = level;
    ndspChnSetMix(channel, mix);
}

static const unsigned char *slot_pcm(int index)
{
    if (index < 0 || index >= BANJO_FOOT_PCM_COUNT || !banjo_foot_pcm[index].present)
        return NULL;
    return banjo_foot_pcm[index].pcm;
}

static void queue_play(const BanjoFootPlay *play)
{
    int index;
    int channel;
    int slot;
    float level;
    float rate;
    s16 *pcm;

    if (!play)
        return;
    channel = channel_for_source(play->source);
    if (channel < 0)
        return;
    slot = -1;
    for (index = 0; index < BANJO_FOOT_PCM_COUNT; index++) {
        if (banjo_foot_pcm[index].sfx_id == play->sfx_id && banjo_foot_pcm[index].present
            && pcm_buffers[index] && pcm_samples[index] > 0) {
            slot = index;
            break;
        }
    }
    if (slot < 0)
        return;
    pcm = pcm_buffers[slot];
    if (banjo_foot_pcm[slot].volume_known) {
        level = (float)sfxSynthVolume(SFX_LEVEL_TABLE, banjo_foot_pcm[slot].attack_volume,
            play->loudness, banjo_foot_pcm[slot].sample_volume) / 32767.0f;
    } else {
        level = 1.0f;
    }
    rate = banjo_foot_output_rate(play->pitch, banjo_foot_pcm[slot].key_base,
        banjo_foot_pcm[slot].detune, banjo_foot_pcm[slot].omit_detune);
    ndspChnWaveBufClear(channel);
    configure_channel(channel, rate, level);
    memset(&waves[play->source], 0, sizeof(waves[play->source]));
    waves[play->source].data_pcm16 = pcm;
    waves[play->source].nsamples = pcm_samples[slot];
    waves[play->source].looping = false;
    waves[play->source].status = NDSP_WBUF_FREE;
    ndspChnWaveBufAdd(channel, &waves[play->source]);
}

void footstep3dsInit(void)
{
    int index;

    for (index = 0; index < BANJO_FOOT_PCM_COUNT; index++) {
        free_pcm(&pcm_buffers[index]);
        pcm_samples[index] = 0;
    }
    memset(waves, 0, sizeof(waves));
    staged = 0;
    if (!sfxProbe3dsReady())
        return;
    for (index = 0; index < BANJO_FOOT_PCM_COUNT; index++) {
        const unsigned char *src = slot_pcm(index);
        u32 bytes;

        if (!src)
            continue;
        bytes = (u32)banjo_foot_pcm[index].bytes;
        pcm_buffers[index] = stage_pcm(src, bytes);
        if (pcm_buffers[index])
            pcm_samples[index] = bytes / sizeof(s16);
    }
    ndspChnReset(1);
    ndspChnReset(2);
    staged = 1;
}

void footstep3dsSubmit(const BanjoFootPlay *plays, int count)
{
    int index;

    if (!plays || count <= 0 || !staged || !sfxProbe3dsReady())
        return;
    for (index = 0; index < count && index < 2; index++)
        queue_play(&plays[index]);
}

void footstep3dsExit(void)
{
    int index;

    if (sfxProbe3dsReady()) {
        ndspChnWaveBufClear(1);
        ndspChnWaveBufClear(2);
    }
    for (index = 0; index < BANJO_FOOT_PCM_COUNT; index++) {
        free_pcm(&pcm_buffers[index]);
        pcm_samples[index] = 0;
    }
    memset(waves, 0, sizeof(waves));
    staged = 0;
}
