/**
 * @file top_memory_tier.cpp
 * @brief Memory-tier knob: codebook loaded into an INTERNAL array so bind_storage
 *        can place it in BRAM or URAM.
 */
#include <ap_int.h>
#include <hls_stream.h>
#include "common/hdc_types.hpp"
#include "memory/gather.hpp"

#define MEM_N    128
#define MEM_D    256    // aligned with characterize sweep (was 1024)

#ifndef MEM_DP
#define MEM_DP   1
#endif
#ifndef USE_URAM
#define USE_URAM 0
#endif


void memory_tier_top(hls::stream<hdc::binary_t> &codebook_in,
                     int index, hdc::binary_t out[MEM_D]) {
    // Internal on-chip codebook -- the memory whose tier we control.
    static hdc::binary_t codebook[MEM_N][MEM_D];
#if USE_URAM
    #pragma HLS bind_storage variable=codebook type=RAM_2P impl=URAM
#else
    #pragma HLS bind_storage variable=codebook type=RAM_2P impl=BRAM
#endif
    // Load once from the stream. A stream is read in order, so HLS MUST buffer
    // it into 'codebook' -- that is what keeps the memory real (not optimized away).
    LOAD_N: for (int n = 0; n < MEM_N; n++)
        LOAD_D: for (int i = 0; i < MEM_D; i++)
            codebook[n][i] = codebook_in.read();

    hdc::gather<hdc::binary_t, MEM_N, MEM_D, MEM_DP>(codebook, index, out);
}