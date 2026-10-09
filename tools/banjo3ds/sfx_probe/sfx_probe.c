#include "sfx_probe.h"

static int clip_usable(int bytes)
{
    return bytes >= 2 && (bytes % 2) == 0;
}

void sfxProbeReset(SfxProbe *probe)
{
    if (!probe)
        return;
    probe->ndsp_ready = 0;
    probe->landing_bytes = 0;
    probe->slide_bytes = 0;
    probe->sample_rate = 0;
    probe->phase = SFX_PROBE_IDLE;
    probe->clip = SFX_PROBE_CLIP_LANDING;
    probe->armed = 0;
    probe->queue_count = 0;
    probe->release_count = 0;
    probe->gap_start_ms = 0;
}

int sfxProbeBind(SfxProbe *probe, int ndsp_ready, int landing_bytes, int slide_bytes, int sample_rate)
{
    int landing_ok;
    int slide_ok;

    if (!probe || probe->phase != SFX_PROBE_IDLE || probe->armed)
        return 0;
    probe->ndsp_ready = ndsp_ready;
    probe->landing_bytes = landing_bytes;
    probe->slide_bytes = slide_bytes;
    probe->sample_rate = sample_rate;
    landing_ok = clip_usable(landing_bytes);
    slide_ok = clip_usable(slide_bytes);
    if (!ndsp_ready || sample_rate != SFX_PROBE_RATE || (!landing_ok && !slide_ok)) {
        probe->phase = SFX_PROBE_SKIPPED;
        return 0;
    }
    /* Slide-only starts on SFX_18. Otherwise SFX_19 plays first. */
    probe->clip = landing_ok ? SFX_PROBE_CLIP_LANDING : SFX_PROBE_CLIP_SLIDE;
    probe->armed = 1;
    return 1;
}

int sfxProbePoll(SfxProbe *probe, int now_ms)
{
    if (!probe || !probe->armed)
        return 0;
    if (probe->phase == SFX_PROBE_IDLE) {
        probe->phase = SFX_PROBE_QUEUED;
        probe->queue_count += 1;
        return 1;
    }
    if (probe->phase == SFX_PROBE_GAP) {
        /* Unsigned subtraction stays correct when (int)osGetTime() wraps. */
        if ((unsigned)now_ms - (unsigned)probe->gap_start_ms < (unsigned)SFX_PROBE_GAP_MS)
            return 0;
        probe->clip = SFX_PROBE_CLIP_SLIDE;
        probe->phase = SFX_PROBE_QUEUED;
        probe->queue_count += 1;
        return 1;
    }
    return 0;
}

void sfxProbeComplete(SfxProbe *probe, int now_ms)
{
    if (!probe || probe->phase != SFX_PROBE_QUEUED)
        return;
    if (probe->clip == SFX_PROBE_CLIP_LANDING && clip_usable(probe->slide_bytes)) {
        probe->phase = SFX_PROBE_GAP;
        probe->gap_start_ms = now_ms;
        return;
    }
    probe->phase = SFX_PROBE_DONE;
}

int sfxProbeShutdown(SfxProbe *probe)
{
    if (!probe)
        return 0;
    if (probe->phase == SFX_PROBE_QUEUED) {
        probe->phase = SFX_PROBE_DONE;
        probe->release_count += 1;
        return 1;
    }
    if (probe->phase == SFX_PROBE_GAP) {
        probe->phase = SFX_PROBE_DONE;
        return 0;
    }
    return 0;
}
