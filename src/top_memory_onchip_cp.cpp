/**
 * @file top_memory_onchip_cp.cpp
 * @brief ON-CHIP reference for the off-chip streaming comparison: the codebook is
 *        RESIDENT in on-chip RAM (BRAM or URAM) and read directly, which is what
 *        prior FPGA-HDC accelerators do (Hyle, F5-HD, HD2FPGA all fix codebooks on
 *        chip). This is the tier the streaming SME must be judged against, because
 *        it is the alternative way of solving the same problem -- not a slower
 *        variant of our own design.
 *
 *        Matched to top_memory_offchip_cp.cpp / top_hbm_gather_cp_df.cpp on every
 *        axis that could otherwise explain a difference:
 *          - same D (TD=8192) and codebook depth (TN=64 rows per channel)
 *          - same HBM_CP independent channels, each its own banked array
 *          - same word width (HBM_WBITS) and same words-per-row (WPR)
 *          - same compute: XOR fold + parity reduce, identical to `sink`
 *          - same top-level interface (s_axilite index, ap_memory out)
 *
 *        The difference is the memory tier. On chip there is no AXI round trip and
 *        no burst structure, so no FIFO or buffer stage is needed: the read and the
 *        fold fuse into one II=1 loop. That is the on-chip advantage, and measuring
 *        it is the point.
 *
 *        The codebook arrays are declared INSIDE the kernel so their storage cost
 *        appears in the synthesis report. That is what makes the capacity ceiling
 *        visible: at TN=64 x CP=8 the codebook is 4.2 Mbit, but a realistic item
 *        memory (N >> 64) will not fit, which is precisely why the off-chip path
 *        exists.
 *
 *        Build with -DMEM_URAM=1 to place the codebook in URAM instead of BRAM.
 *        Swept over HBM_CP by scripts/sweep_memory_onchip_cp.tcl.
 */
#include <ap_int.h>
#include "common/hdc_types.hpp"

#ifndef HBM_WBITS
#define HBM_WBITS 512
#endif
#ifndef HBM_CP
#define HBM_CP 8
#endif

#define TN 64                       // hypervectors per channel
#define TD 8192                     // hv_dim in bits
#define WPR (TD / HBM_WBITS)        // words per hypervector
#define ROWS (TN * WPR)             // words per channel array

typedef ap_uint<HBM_WBITS> word_t;

// Same final reduce as the off-chip designs' sink, so the compute is identical.
static hdc::binary_t fold_parity(word_t acc) {
    hdc::binary_t p = 0;
REDUCE:
    for (int b = 0; b < HBM_WBITS; b++) {
        #pragma HLS UNROLL
        p ^= (hdc::binary_t)acc[b];
    }
    return p;
}

void memory_onchip_cp_top(int index, hdc::binary_t out[HBM_CP]) {
    #pragma HLS INTERFACE s_axilite port=index
    #pragma HLS INTERFACE ap_memory  port=out
    #pragma HLS INTERFACE s_axilite port=return
    #pragma HLS ARRAY_PARTITION variable=out complete dim=1

    // ---- resident codebook: one banked array per channel ----
    static word_t bank0[ROWS];
#if MEM_URAM
    #pragma HLS bind_storage variable=bank0 type=RAM_2P impl=URAM
#else
    #pragma HLS bind_storage variable=bank0 type=RAM_2P impl=BRAM
#endif
#if HBM_CP >= 2
    static word_t bank1[ROWS];
#if MEM_URAM
    #pragma HLS bind_storage variable=bank1 type=RAM_2P impl=URAM
#else
    #pragma HLS bind_storage variable=bank1 type=RAM_2P impl=BRAM
#endif
#endif
#if HBM_CP >= 4
    static word_t bank2[ROWS];
    static word_t bank3[ROWS];
#if MEM_URAM
    #pragma HLS bind_storage variable=bank2 type=RAM_2P impl=URAM
    #pragma HLS bind_storage variable=bank3 type=RAM_2P impl=URAM
#else
    #pragma HLS bind_storage variable=bank2 type=RAM_2P impl=BRAM
    #pragma HLS bind_storage variable=bank3 type=RAM_2P impl=BRAM
#endif
#endif
#if HBM_CP >= 8
    static word_t bank4[ROWS];
    static word_t bank5[ROWS];
    static word_t bank6[ROWS];
    static word_t bank7[ROWS];
#if MEM_URAM
    #pragma HLS bind_storage variable=bank4 type=RAM_2P impl=URAM
    #pragma HLS bind_storage variable=bank5 type=RAM_2P impl=URAM
    #pragma HLS bind_storage variable=bank6 type=RAM_2P impl=URAM
    #pragma HLS bind_storage variable=bank7 type=RAM_2P impl=URAM
#else
    #pragma HLS bind_storage variable=bank4 type=RAM_2P impl=BRAM
    #pragma HLS bind_storage variable=bank5 type=RAM_2P impl=BRAM
    #pragma HLS bind_storage variable=bank6 type=RAM_2P impl=BRAM
    #pragma HLS bind_storage variable=bank7 type=RAM_2P impl=BRAM
#endif
#endif

    const int base = index * WPR;

    word_t acc0 = 0;
#if HBM_CP >= 2
    word_t acc1 = 0;
#endif
#if HBM_CP >= 4
    word_t acc2 = 0, acc3 = 0;
#endif
#if HBM_CP >= 8
    word_t acc4 = 0, acc5 = 0, acc6 = 0, acc7 = 0;
#endif

    // ---- read + fold fused: on-chip RAM needs no staging buffer and no FIFO ----
READ_FOLD:
    for (int w = 0; w < WPR; w++) {
        #pragma HLS PIPELINE II=1
        acc0 ^= bank0[base + w];
#if HBM_CP >= 2
        acc1 ^= bank1[base + w];
#endif
#if HBM_CP >= 4
        acc2 ^= bank2[base + w];
        acc3 ^= bank3[base + w];
#endif
#if HBM_CP >= 8
        acc4 ^= bank4[base + w];
        acc5 ^= bank5[base + w];
        acc6 ^= bank6[base + w];
        acc7 ^= bank7[base + w];
#endif
    }

    out[0] = fold_parity(acc0);
#if HBM_CP >= 2
    out[1] = fold_parity(acc1);
#endif
#if HBM_CP >= 4
    out[2] = fold_parity(acc2);
    out[3] = fold_parity(acc3);
#endif
#if HBM_CP >= 8
    out[4] = fold_parity(acc4);
    out[5] = fold_parity(acc5);
    out[6] = fold_parity(acc6);
    out[7] = fold_parity(acc7);
#endif
}
