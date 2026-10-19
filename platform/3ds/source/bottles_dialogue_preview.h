#ifndef BANJO3DS_BOTTLES_DIALOGUE_PREVIEW_H
#define BANJO3DS_BOTTLES_DIALOGUE_PREVIEW_H
/* Passive diagnostic observer; no actor writes, input, clock or GPU APIs. */
#include <stdbool.h>
#include <stddef.h>
#include <math.h>
#include "generated_dialogue.h"

#define DP_MAX_COLUMNS 36u
#define DP_MAX_RECORDS 16u

typedef struct { const uint8_t *bytes; uint16_t length; uint8_t speaker; } DpSpeech;
typedef struct { bool armed, fired, active, done; float previous_phase; } DpPreview;

static inline const BanjoDialogueResource *dpLookup(const BanjoDialogueResource *data, size_t count)
{
    const BanjoDialogueResource *found = NULL;
    if (!data || count > BANJO_DIALOGUE_RESOURCE_COUNT) return NULL;
    for (size_t i = 0; i < count; ++i) {
        if (data[i].resource_id != 0xDF4) continue;
        if (found) return NULL;
        found = &data[i];
    }
    return found;
}

/* Capacities must describe the actual immutable backing arrays, not record fields. */
static inline bool dpFirstSpeech(const BanjoDialogueResource *r, size_t text_capacity,
    const size_t capacities[2], DpSpeech *out)
{
    if (!out) return false;
    *out = (DpSpeech){0};
    if (!r || !capacities || r->resource_id != 0xDF4 || !r->text ||
        r->text_length > text_capacity || r->text_length > 1024) return false;
    for (size_t s = 0; s < 2; ++s) {
        const BanjoDialogueStream *stream = &r->streams[s];
        if (!stream->records || stream->identity != s || !stream->count ||
            stream->count > capacities[s] || stream->count > DP_MAX_RECORDS) return false;
        for (size_t i = 0; i < stream->count; ++i) {
            const BanjoDialogueRecord *rec = &stream->records[i];
            if (rec->text_offset > r->text_length || rec->text_length > 254 ||
                rec->text_length > r->text_length - rec->text_offset) return false;
            if (rec->opcode == 4 || rec->opcode == 6) {
                if (rec->text_length || rec->speaker != 255 || rec->portrait != 255) return false;
                if (rec->opcode == 4 && i + 1 != stream->count) return false;
            } else if (rec->opcode == 0x80 || rec->opcode == 0x81 || rec->opcode == 0x83) {
                if (rec->speaker != rec->opcode - 0x80 || rec->portrait != rec->speaker + 12)
                    return false;
            } else return false;
        }
        if (stream->records[stream->count - 1].opcode != 4) return false;
    }
    /* Rare gc/dialog.c:724: bottom if its initial command is a control, else top. */
    unsigned active = r->streams[0].records[0].opcode < 0x20 ? 0 : 1;
    size_t position[2] = {0, 0};
    for (size_t steps = 0; steps < 2 * DP_MAX_RECORDS; ++steps) {
        const BanjoDialogueStream *stream = &r->streams[active];
        if (position[active] >= stream->count) {
            if (position[active ^ 1] >= r->streams[active ^ 1].count) return false;
            active ^= 1;
            continue;
        }
        const BanjoDialogueRecord *rec = &stream->records[position[active]++];
        if (rec->opcode == 4 || rec->opcode == 6) { active ^= 1; continue; }
        if (!rec->text_length) continue;
        /* One printable diagnostic line; reject escape/control bytes, never replace. */
        if (rec->speaker != 0 || rec->text_length > DP_MAX_COLUMNS) return false;
        for (size_t i = 0; i < rec->text_length; ++i)
            if (r->text[rec->text_offset+i] < 0x20 || r->text[rec->text_offset+i] > 0x7e)
                return false;
        *out = (DpSpeech){r->text + rec->text_offset, rec->text_length, rec->speaker};
        return true;
    }
    return false;
}

static inline bool dpSelectGenerated(DpSpeech *out)
{
    const BanjoDialogueResource *r = dpLookup(banjo_dialogue_resources, BANJO_DIALOGUE_RESOURCE_COUNT);
    const size_t cap[2] = { sizeof banjo_dialogue_0df4_bottom / sizeof(BanjoDialogueRecord),
                           sizeof banjo_dialogue_0df4_top / sizeof(BanjoDialogueRecord) };
    if (!r || r->text != banjo_dialogue_0df4_text ||
        r->streams[0].records != banjo_dialogue_0df4_bottom ||
        r->streams[1].records != banjo_dialogue_0df4_top) return false;
    return dpFirstSpeech(r, sizeof banjo_dialogue_0df4_text, cap, out);
}

/* Return a presentation change only. Phase is the approved actor's phase. */
static inline bool dpObserve(DpPreview *p, bool emerging, bool idle, bool exiting, float phase)
{
    if (!p) return false;
    bool before = p->active;
    if (exiting) { p->active = false; p->done = true; }
    if (p->done) return before != p->active;
    if (!isfinite(phase) || phase < 0 || phase > 1) return false;
    if (emerging) p->armed = true;
    if (p->armed && (emerging || idle)) {
        if (!p->fired && p->previous_phase < 0.35f && phase >= 0.35f) {
            p->active = true;
            p->fired = true;
        }
        p->previous_phase = phase;
    }
    return before != p->active;
}
#if BANJO3DS_ACTOR_BOTTLES_DIALOGUE_SEQUENCE
/* Diagnostic timing and layout, not Rare zoombox timing. No input ownership. */
#define DS_MAX_LINES 8u
#define DS_MAX_VISITS (2u * DP_MAX_RECORDS)
#define DS_BASE_SECONDS 2.0
#define DS_SECONDS_PER_BYTE 0.06
#define DS_MIN_SECONDS 3.0
#define DS_MAX_SECONDS 9.0
#define DS_MAX_DELTA 0.25
#define DS_CONSOLE_USED_ROWS 12u

typedef struct { uint16_t offset[DS_MAX_LINES]; uint8_t length[DS_MAX_LINES], count; } DsLayout;
typedef enum { DS_WAITING, DS_ACTIVE, DS_COMPLETED, DS_CANCELED, DS_FAILED } DsStatus;
typedef struct {
    const BanjoDialogueResource *resource;
    size_t text_capacity, capacity[2];
    unsigned stream, index[2], visits;
    bool closed[2];
    DsStatus status;
    DpSpeech speech;
    DsLayout layout;
    double elapsed;
} DsSequence;

static inline const char *dsSpeakerLabel(uint8_t speaker)
{
    switch (speaker) { case 0: return "BANJO"; case 1: return "KAZOOIE";
                      case 3: return "BOTTLES"; default: return NULL; }
}

/* Preserve every byte: space at a wrap stays at the end of the preceding row. */
static inline bool dsWrap(const uint8_t *bytes, size_t length, DsLayout *out)
{
    if (!out) return false;
    *out = (DsLayout){0};
    if (!bytes || !length || length > 254) return false;
    for (size_t i = 0; i < length; ++i)
        if (bytes[i] < 0x20 || bytes[i] > 0x7e) return false;
    DsLayout layout = {0};
    size_t position = 0;
    for (unsigned line = 0; line < DS_MAX_LINES && position < length; ++line) {
        size_t count = length - position;
        if (count > DP_MAX_COLUMNS) {
            count = DP_MAX_COLUMNS;
            for (size_t j = count; j > 0; --j)
                if (bytes[position + j - 1] == ' ') { count = j; break; }
        }
        layout.offset[line] = (uint16_t)position;
        layout.length[line] = (uint8_t)count;
        ++layout.count;
        position += count;
    }
    if (position != length) return false; /* Never publish a truncated layout. */
    *out = layout;
    return true;
}

static inline bool dsValidate(const BanjoDialogueResource *r, size_t text_capacity,
    const size_t capacity[2])
{
    DpSpeech first;
    /* Reuse approved metadata/bounds/first-Banjo validation without altering it. */
    if (!dpFirstSpeech(r, text_capacity, capacity, &first)) return false;
    for (unsigned s = 0; s < 2; ++s)
        for (unsigned i = 0; i < r->streams[s].count; ++i) {
            const BanjoDialogueRecord *rec = &r->streams[s].records[i];
            DsLayout layout;
            if (rec->text_length && !dsWrap(r->text + rec->text_offset, rec->text_length, &layout))
                return false;
        }
    return true;
}

static inline bool dsFinish(DsSequence *p, DsStatus status)
{
    p->status = status;
    p->speech = (DpSpeech){0};
    p->layout = (DsLayout){0};
    p->elapsed = 0;
    return true; /* One visible-content change; terminal calls return false. */
}

static inline bool dsNext(DsSequence *p)
{
    if (!p || p->status != DS_ACTIVE) return false;
    if (!dsValidate(p->resource, p->text_capacity, p->capacity) || p->stream > 1 ||
        p->visits > DS_MAX_VISITS) return dsFinish(p, DS_FAILED);
    for (unsigned s = 0; s < 2; ++s)
        if (p->index[s] > p->resource->streams[s].count ||
            (p->closed[s] && p->index[s] != p->resource->streams[s].count))
            return dsFinish(p, DS_FAILED);
    for (unsigned step = 0; step < DS_MAX_VISITS; ++step) {
        if (p->closed[0] && p->closed[1]) return dsFinish(p, DS_COMPLETED);
        if (p->closed[p->stream]) { p->stream ^= 1; continue; }
        const BanjoDialogueStream *stream = &p->resource->streams[p->stream];
        if (p->index[p->stream] >= stream->count || p->visits >= DS_MAX_VISITS)
            return dsFinish(p, DS_FAILED);
        const BanjoDialogueRecord *rec = &stream->records[p->index[p->stream]++];
        ++p->visits;
        if (rec->opcode == 4) { p->closed[p->stream] = true; p->stream ^= 1; continue; }
        if (rec->opcode == 6) { p->stream ^= 1; continue; }
        if (!rec->text_length) continue;
        p->speech = (DpSpeech){p->resource->text + rec->text_offset, rec->text_length, rec->speaker};
        if (!dsWrap(p->speech.bytes, p->speech.length, &p->layout)) return dsFinish(p, DS_FAILED);
        p->elapsed = 0;
        return true;
    }
    if (p->closed[0] && p->closed[1]) return dsFinish(p, DS_COMPLETED);
    return dsFinish(p, DS_FAILED);
}

static inline bool dsBegin(DsSequence *p, const BanjoDialogueResource *r,
    size_t text_capacity, const size_t capacity[2])
{
    if (!p || p->status != DS_WAITING) return false;
    if (!dsValidate(r, text_capacity, capacity)) return dsFinish(p, DS_FAILED);
    *p = (DsSequence){0};
    p->resource = r;
    p->text_capacity = text_capacity;
    p->capacity[0] = capacity[0]; p->capacity[1] = capacity[1];
    p->stream = r->streams[0].records[0].opcode < 0x20 ? 0 : 1;
    p->status = DS_ACTIVE;
    return dsNext(p);
}

static inline bool dsBeginGenerated(DsSequence *p)
{
    const BanjoDialogueResource *r = dpLookup(banjo_dialogue_resources, BANJO_DIALOGUE_RESOURCE_COUNT);
    const size_t cap[2] = {sizeof banjo_dialogue_0df4_bottom / sizeof(BanjoDialogueRecord),
                          sizeof banjo_dialogue_0df4_top / sizeof(BanjoDialogueRecord)};
    return dsBegin(p, r, sizeof banjo_dialogue_0df4_text, cap);
}

static inline double dsDuration(uint16_t length)
{
    double seconds = DS_BASE_SECONDS + DS_SECONDS_PER_BYTE * length;
    if (seconds < DS_MIN_SECONDS) seconds = DS_MIN_SECONDS;
    if (seconds > DS_MAX_SECONDS) seconds = DS_MAX_SECONDS;
    return seconds;
}

static inline bool dsTick(DsSequence *p, double dt)
{
    if (!p || p->status != DS_ACTIVE || !isfinite(dt) || dt < 0) return false;
    if (dt > DS_MAX_DELTA) dt = DS_MAX_DELTA;
    p->elapsed += dt;
    if (p->elapsed < dsDuration(p->speech.length)) return false;
    /* At most one speech transition/update; no skipped entry after a hitch. */
    return dsNext(p);
}

static inline bool dsCancel(DsSequence *p)
{
    if (!p || (p->status != DS_ACTIVE && p->status != DS_WAITING)) return false;
    bool visible = p->status == DS_ACTIVE;
    dsFinish(p, DS_CANCELED);
    return visible;
}

/* libctru RGB565 framebuffer is column-major, vertically inverted. Clear only
 * console rows 1..12 (all possible text), preserving the unused lower screen. */
static inline bool dsClearTextArea(uint16_t *pixels, size_t count)
{
    if (!pixels || count < 320u * 240u) return false;
    for (size_t x = 0; x < 320; ++x)
        for (size_t y = 240u - DS_CONSOLE_USED_ROWS * 8u; y < 240; ++y)
            pixels[x * 240 + y] = 0;
    return true;
}
#endif
#endif
