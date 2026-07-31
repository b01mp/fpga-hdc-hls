/**
 * @file top_hbm_gather_cp_df.cpp
 * @brief Class-parallel streaming gather WITH fetch/compute overlap. The CP producer
 *        (hbm_gather_cp -- HERA-style independent channels) is placed inside a
 *        #pragma HLS DATAFLOW region, where each channel drains through its own deep
 *        FIFO into a concurrent consumer (NysX-style overlap). Unlike the
 *        characterization top (top_hbm_gather_cp.cpp, producer -> AXIS, no consumer),
 *        producer and consumers run CONCURRENTLY, decoupled by the FIFOs, so a
 *        channel's DRAM latency is hidden behind the consumer's compute.
 *
 *        The consumer is a lightweight per-channel checksum sink that pulls one wide
 *        word per cycle (II=1), standing in for the real compute stage (bind /
 *        bundle / similarity). It deliberately avoids the single-port array-drain
 *        artifact of the demo `unpack` in top_hbm_gather.cpp.
 *
 *        Swept over HBM_CP by scripts/sweep_hbm_gather_cp_df.tcl -> the "with FIFO
 *        overlap" latency/II column (vs top_hbm_gather_cp.cpp = without).
 */
#include <ap_int.h>
#include <hls_stream.h>
#include "common/hdc_types.hpp"
#include "memory/hbm_gather_cp.hpp"

#define TN 64
#define TD 8192

#ifndef HBM_OUTSTANDING
#define HBM_OUTSTANDING 16
#endif
#ifndef HBM_FIFO_DEPTH
#define HBM_FIFO_DEPTH  64        // deep FIFO: decouples each CRE's bursts from its consumer
#endif

// Per-channel consumer: drain WPR wide words at II=1, fold to a 1-bit checksum.
// Stands in for the real compute stage; runs concurrently with the producer.
static void sink(hls::stream<hdc::hbm_word_t> &in, hdc::binary_t &out) {
    const int WPR = TD / HBM_WBITS;
    hdc::hbm_word_t acc = 0;
DRAIN:
    for (int w = 0; w < WPR; w++) {
        #pragma HLS PIPELINE II=1
        acc ^= in.read();
    }
    hdc::binary_t p = 0;
REDUCE:
    for (int b = 0; b < HBM_WBITS; b++) {
        #pragma HLS UNROLL
        p ^= (hdc::binary_t)acc[b];
    }
    out = p;
}

void hbm_gather_cp_df_top(
        const hdc::hbm_word_t *bank0,
#if HBM_CP >= 2
        const hdc::hbm_word_t *bank1,
#endif
#if HBM_CP >= 4
        const hdc::hbm_word_t *bank2, const hdc::hbm_word_t *bank3,
#endif
#if HBM_CP >= 8
        const hdc::hbm_word_t *bank4, const hdc::hbm_word_t *bank5,
        const hdc::hbm_word_t *bank6, const hdc::hbm_word_t *bank7,
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

    #pragma HLS DATAFLOW

    // One deep FIFO per channel: this is what makes the read/compute overlap real.
    hls::stream<hdc::hbm_word_t> fifo0;
    #pragma HLS STREAM variable=fifo0 depth=HBM_FIFO_DEPTH
#if HBM_CP >= 2
    hls::stream<hdc::hbm_word_t> fifo1;
    #pragma HLS STREAM variable=fifo1 depth=HBM_FIFO_DEPTH
#endif
#if HBM_CP >= 4
    hls::stream<hdc::hbm_word_t> fifo2;
    #pragma HLS STREAM variable=fifo2 depth=HBM_FIFO_DEPTH
    hls::stream<hdc::hbm_word_t> fifo3;
    #pragma HLS STREAM variable=fifo3 depth=HBM_FIFO_DEPTH
#endif
#if HBM_CP >= 8
    hls::stream<hdc::hbm_word_t> fifo4;
    #pragma HLS STREAM variable=fifo4 depth=HBM_FIFO_DEPTH
    hls::stream<hdc::hbm_word_t> fifo5;
    #pragma HLS STREAM variable=fifo5 depth=HBM_FIFO_DEPTH
    hls::stream<hdc::hbm_word_t> fifo6;
    #pragma HLS STREAM variable=fifo6 depth=HBM_FIFO_DEPTH
    hls::stream<hdc::hbm_word_t> fifo7;
    #pragma HLS STREAM variable=fifo7 depth=HBM_FIFO_DEPTH
#endif

    // Producer task: HBM_CP independent CREs stream row `index` into the FIFOs.
    hdc::hbm_gather_cp<TN, TD>(bank0,
#if HBM_CP >= 2
        bank1,
#endif
#if HBM_CP >= 4
        bank2, bank3,
#endif
#if HBM_CP >= 8
        bank4, bank5, bank6, bank7,
#endif
        index, fifo0
#if HBM_CP >= 2
        , fifo1
#endif
#if HBM_CP >= 4
        , fifo2, fifo3
#endif
#if HBM_CP >= 8
        , fifo4, fifo5, fifo6, fifo7
#endif
        );

    // Consumer tasks: one per channel, draining concurrently with the producer.
    sink(fifo0, out[0]);
#if HBM_CP >= 2
    sink(fifo1, out[1]);
#endif
#if HBM_CP >= 4
    sink(fifo2, out[2]);
    sink(fifo3, out[3]);
#endif
#if HBM_CP >= 8
    sink(fifo4, out[4]);
    sink(fifo5, out[5]);
    sink(fifo6, out[6]);
    sink(fifo7, out[7]);
#endif
}