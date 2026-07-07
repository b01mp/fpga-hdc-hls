#include <ap_int.h>
#include "common/hdc_types.hpp"
#include "generation/random_hv.hpp"

#define GEN_D 256
#define GEN_F 4

void generation_random_hv_top(hdc::binary_t codebook[GEN_F][GEN_D]) {
    hdc::random_hv<hdc::binary_t, GEN_D, GEN_F>(codebook);
}