#include <ap_int.h>
#include "common/hdc_types.hpp"
#include "memory/gather.hpp"

#define MEM_D  256
#define MEM_N  10
#define MEM_DP 8

void memory_gather_top(const hdc::binary_t codebook[MEM_N][MEM_D], int index, hdc::binary_t out[MEM_D]) {
    // memory_space: codebook in BRAM (change impl=BRAM -> URAM to try UltraRAM)
    #pragma HLS bind_storage variable=codebook type=RAM_2P impl=BRAM
    hdc::gather<hdc::binary_t, MEM_N, MEM_D, MEM_DP>(codebook, index, out);
}