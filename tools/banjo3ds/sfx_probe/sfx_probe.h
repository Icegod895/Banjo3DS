#ifndef BANJO_SFX_PROBE_H
#define BANJO_SFX_PROBE_H

/* Two-clip listening probe. Both clips play at the N64 AI output clock,
 * osAiSetFrequency(22000) in code_1D00.c. keyBase 60 and detune 0 are unity.
 * The bank field 22050 and the source loudness integer 28000 are not the rate.
 * SFX_19 plays first, then SFX_PROBE_GAP_MS of silence, then unlooped SFX_18.
 * This state machine does not loop, envelope, or walk the pitch. */
#define SFX_PROBE_RATE 22000
#define SFX_PROBE_GAP_MS 400

#define SFX_PROBE_CLIP_LANDING 0
#define SFX_PROBE_CLIP_SLIDE 1

#define SFX_PROBE_IDLE 0
#define SFX_PROBE_QUEUED 1
#define SFX_PROBE_GAP 2
#define SFX_PROBE_DONE 3
#define SFX_PROBE_SKIPPED 4

typedef struct SfxProbe {
    int ndsp_ready;
    int landing_bytes;
    int slide_bytes;
    int sample_rate;
    int phase;
    int clip;
    int armed;
    int queue_count;
    int release_count;
    int gap_start_ms;
} SfxProbe;

void sfxProbeReset(SfxProbe *probe);
int sfxProbeBind(SfxProbe *probe, int ndsp_ready, int landing_bytes, int slide_bytes, int sample_rate);
int sfxProbePoll(SfxProbe *probe, int now_ms);
void sfxProbeComplete(SfxProbe *probe, int now_ms);
int sfxProbeShutdown(SfxProbe *probe);

#endif
