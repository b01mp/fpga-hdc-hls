#include <ap_int.h>
#include "common/hdc_types.hpp"
#include "memory/gather.hpp"

#define MEM_D 256
#define MEM_N 10

void memory_gather_top(const hdc::binary_t codebook[MEM_N][MEM_D], int index, hdc::binary_t out[MEM_D]) {
    hdc::gather<hdc::binary_t, MEM_N, MEM_D>(codebook, index, out);
}