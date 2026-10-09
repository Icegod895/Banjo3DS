#ifndef BANJO_SFX_PROBE_H
#define BANJO_SFX_PROBE_H

/* Slide-lifecycle probe constants.
 * SFX_PROBE_RATE is the N64 AI clock, osAiSetFrequency(22000) in code_1D00.c.
 * The source integers below are loudness, not sample rates:
 * basfx_reset sets 28000 on the SFX_18 voice (basfx.c), and the stop callback
 * basfx_802998D0 plays SFX_19 at the last pitch with 22000.
 * SFX_PROBE_SLIDE_MS is a fixed probe hold. The original voice lasts as long
 * as bsslide_update keeps calling basfx_80299AAC. */
#define SFX_PROBE_RATE 22000
#define SFX_PROBE_SLIDE_MS 2000
#define SFX_SLIDE_SOURCE_VOLUME 28000
#define SFX_CLOSER_SOURCE_VOLUME 22000
#define SFX_LEVEL_TABLE 32767

#endif
