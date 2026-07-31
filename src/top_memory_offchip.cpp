/**
 * @file top_memory_offchip.cpp
 * @brief Off-chip tier: codebook lives in external DDR/HBM, reached over an AXI
 *        master. Only one row is burst-read into a small on-chip buffer.
 */
#include <ap_int.h>
#include "common/hdc_types.hpp"

#define MEM_N 128
#define MEM_D 256    // aligned with characterize sweep (was 1024)

void memory_offchip_top(const hdc::binary_t *codebook,   // flat [N*D] in EXTERNAL memory
                        int index,
                        hdc::binary_t out[MEM_D]) {
    #pragma HLS INTERFACE m_axi     port=codebook offset=slave bundle=gmem
    #pragma HLS INTERFACE s_axilite port=index
    #pragma HLS INTERFACE ap_memory port=out
    #pragma HLS INTERFACE s_axilite port=return

    // small on-chip buffer for ONE row (D elements) -- not the whole codebook
    hdc::binary_t row_buf[MEM_D];
    #pragma HLS bind_storage variable=row_buf type=RAM_2P impl=BRAM

    long base = (long)index * MEM_D;
    LOAD: for (int i = 0; i < MEM_D; i++) {   // burst-read one row from off-chip
        #pragma HLS PIPELINE II=1
        row_buf[i] = codebook[base + i];
    }
    OUT: for (int i = 0; i < MEM_D; i++) {
        #pragma HLS PIPELINE II=1
        out[i] = row_buf[i];
    }
}