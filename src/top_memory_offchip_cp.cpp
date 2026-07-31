/**
 * @file top_memory_offchip_cp.cpp
 * @brief BASELINE off-chip codebook read: a competent, burst-optimized, multi-channel
 *        streaming reader WITHOUT fetch/compute overlap. This is the design that
 *        top_hbm_gather_cp_df.cpp is measured against.
 *
 *        It is deliberately NOT a strawman. It matches the dataflow design on every
 *        axis that could otherwise explain a difference:
 *          - same wide HBM_WBITS-bit AXI words (NOT element-at-a-time)
 *          - same HBM_CP independent channels, one m_axi master each, no sharing
 *          - same num_read_outstanding / max_read_burst_length AXI tuning
 *          - same D (TD) and codebook depth (TN), same binary datatype
 *          - same per-channel compute (XOR fold + parity reduce) -- identical work
 *          - same top-level interface (s_axilite index, ap_memory out)
 *
 *        The SINGLE difference is the memory/compute coupling. Here a whole
 *        hypervector is burst-read into an on-chip row buffer, and only then is it
 *        consumed. The two phases are separated by a barrier, so off-chip latency
 *        is EXPOSED rather than hidden: no FIFO, no DATAFLOW region.
 *
 *        This isolates the fetch/compute overlap as the only independent variable,
 *        so the reported speedup is attributable to it alone.
 *
 *        Swept over HBM_CP by scripts/sweep_memory_offchip_cp.tcl.
 *        NOTE: distinct from src/top_memory_offchip.cpp, which remains the D=256
 *        single-port design used by the BRAM/URAM/off-chip memory-TIER sweep.
 */
#include <ap_int.h>
#include "common/hdc_types.hpp"

#ifndef HBM_WBITS
#define HBM_WBITS 512
#endif
#ifndef HBM_CP
#define HBM_CP 8
#endif
#ifndef HBM_OUTSTANDING
#define HBM_OUTSTANDING 16
#endif

#define TN 64                       // hypervectors per channel (address space)
#define TD 8192                     // hv_dim in bits -- matches the dataflow top
#define WPR (TD / HBM_WBITS)        // packed words per hypervector

typedef ap_uint<HBM_WBITS> word_t;

// Final reduce: wide accumulator -> one bit. Identical to the dataflow design's
// sink, so the two designs perform exactly the same compute.
static hdc::binary_t fold_parity(word_t acc) {
    hdc::binary_t p = 0;
REDUCE:
    for (int b = 0; b < HBM_WBITS; b++) {
        #pragma HLS UNROLL
        p ^= (hdc::binary_t)acc[b];
    }
    return p;
}

void memory_offchip_cp_top(
        const word_t *bank0,
#if HBM_CP >= 2
        const word_t *bank1,
#endif
#if HBM_CP >= 4
        const word_t *bank2, const word_t *bank3,
#endif
#if HBM_CP >= 8
        const word_t *bank4, const word_t *bank5,
        const word_t *bank6, const word_t *bank7,
#endif
        int index,
        hdc::binary_t out[HBM_CP]) {
    #pragma HLS INTERFACE m_axi port=bank0 offset=slave bundle=gmem0 num_read_outstanding=HBM_OUTSTANDING max_read_burst_length=64
#if HBM_CP >= 2
    #pragma HLS INTERFACE m_axi port=bank1 offset=slave bundle=gmem1 num_read_outstanding=HBM_OUTSTANDING max_read_burst_length=64
#endif
#if HBM_CP >= 4
    #pragma HLS INTERFACE m_axi port=bank2 offset=slave bundle=gmem2 num_read_outstanding=HBM_OUTSTANDING max_read_burst_length=64
    #pragma HLS INTERFACE m_axi port=bank3 offset=slave bundle=gmem3 num_read_outstanding=HBM_OUTSTANDING max_read_burst_length=64
#endif
#if HBM_CP >= 8
    #pragma HLS INTERFACE m_axi port=bank4 offset=slave bundle=gmem4 num_read_outstanding=HBM_OUTSTANDING max_read_burst_length=64
    #pragma HLS INTERFACE m_axi port=bank5 offset=slave bundle=gmem5 num_read_outstanding=HBM_OUTSTANDING max_read_burst_length=64
    #pragma HLS INTERFACE m_axi port=bank6 offset=slave bundle=gmem6 num_read_outstanding=HBM_OUTSTANDING max_read_burst_length=64
    #pragma HLS INTERFACE m_axi port=bank7 offset=slave bundle=gmem7 num_read_outstanding=HBM_OUTSTANDING max_read_burst_length=64
#endif
    #pragma HLS INTERFACE s_axilite port=index
    #pragma HLS INTERFACE ap_memory  port=out
    #pragma HLS INTERFACE s_axilite port=return
    #pragma HLS ARRAY_PARTITION variable=out complete dim=1

    const int base = index * WPR;

    // ---- on-chip row buffers: one full hypervector per channel ----
    // This is what replaces the dataflow design's FIFO. A buffer must be FILLED
    // before it can be READ, which is precisely what serializes the two phases.
    word_t buf0[WPR];
    #pragma HLS bind_storage variable=buf0 type=RAM_2P impl=BRAM
#if HBM_CP >= 2
    word_t buf1[WPR];
    #pragma HLS bind_storage variable=buf1 type=RAM_2P impl=BRAM
#endif
#if HBM_CP >= 4
    word_t buf2[WPR];
    #pragma HLS bind_storage variable=buf2 type=RAM_2P impl=BRAM
    word_t buf3[WPR];
    #pragma HLS bind_storage variable=buf3 type=RAM_2P impl=BRAM
#endif
#if HBM_CP >= 8
    word_t buf4[WPR];
    #pragma HLS bind_storage variable=buf4 type=RAM_2P impl=BRAM
    word_t buf5[WPR];
    #pragma HLS bind_storage variable=buf5 type=RAM_2P impl=BRAM
    word_t buf6[WPR];
    #pragma HLS bind_storage variable=buf6 type=RAM_2P impl=BRAM
    word_t buf7[WPR];
    #pragma HLS bind_storage variable=buf7 type=RAM_2P impl=BRAM
#endif

    // ---- PHASE 1: burst load. All HBM_CP channels stream concurrently at II=1,
    // exactly as in the dataflow design's producer. Contiguous + port-aligned, so
    // the accesses are inferred as bursts. ----
LOAD:
    for (int w = 0; w < WPR; w++) {
        #pragma HLS PIPELINE II=1
        buf0[w] = bank0[base + w];
#if HBM_CP >= 2
        buf1[w] = bank1[base + w];
#endif
#if HBM_CP >= 4
        buf2[w] = bank2[base + w];
        buf3[w] = bank3[base + w];
#endif
#if HBM_CP >= 8
        buf4[w] = bank4[base + w];
        buf5[w] = bank5[base + w];
        buf6[w] = bank6[base + w];
        buf7[w] = bank7[base + w];
#endif
    }

    // ---- BARRIER ----
    // No consumer may start until the entire row has landed on chip. This is the
    // one and only structural difference from top_hbm_gather_cp_df.cpp.

    // ---- PHASE 2: compute from the on-chip buffers, all channels in parallel. ----
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
COMPUTE:
    for (int w = 0; w < WPR; w++) {
        #pragma HLS PIPELINE II=1
        acc0 ^= buf0[w];
#if HBM_CP >= 2
        acc1 ^= buf1[w];
#endif
#if HBM_CP >= 4
        acc2 ^= buf2[w];
        acc3 ^= buf3[w];
#endif
#if HBM_CP >= 8
        acc4 ^= buf4[w];
        acc5 ^= buf5[w];
        acc6 ^= buf6[w];
        acc7 ^= buf7[w];
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
