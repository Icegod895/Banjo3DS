/* Test-only, pointer-free packed-float32 observations. No algorithm decisions. */
#ifndef BODY_FRAME_OBSERVER_H
#define BODY_FRAME_OBSERVER_H
#include <stdint.h>
typedef struct {
 uint32_t floors,spheres,moving,lines;
 uint32_t parity[5];
 float candidate[5][3];
 uint8_t before[5][120],after[5][120];
} BodyFrameObservation;
#endif
