/* Proven manual controller, borrowing the same published bridge query views.
 * No math fork: only its external contact dependencies use overlay reads. */
#define bc_contact bridge_contact
#define bc_free_b_finish_phase bridge_free_b_finish_phase
#include "../camera_manual/manual.c"
