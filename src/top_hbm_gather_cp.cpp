/**
 * @file top_hbm_gather_cp.cpp
 * @brief Char/synth top for the class-parallel streaming gather. Owns HBM_CP wide
 *        m_axi ports (each with multiple outstanding reads) and exposes HBM_CP
 *        AXI-Stream outputs. No consumer -- so csynth measures the real multi-
 *        channel off-chip access. A real pipeline replaces the streams' sink with
 *        the compute (bind/bundle/similarity) composed later.
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

void hbm_gather_cp_top(
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
        hls::stream<hdc::hbm_word_t> &out0
#if HBM_CP >= 2
        , hls::stream<hdc::hbm_word_t> &out1
#endif
#if HBM_CP >= 4
        , hls::stream<hdc::hbm_word_t> &out2, hls::stream<hdc::hbm_word_t> &out3
#endif
#if HBM_CP >= 8
        , hls::stream<hdc::hbm_word_t> &out4, hls::stream<hdc::hbm_word_t> &out5
        , hls::stream<hdc::hbm_word_t> &out6, hls::stream<hdc::hbm_word_t> &out7
#endif
        ) {
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
    #pragma HLS INTERFACE axis port=out0
#if HBM_CP >= 2
    #pragma HLS INTERFACE axis port=out1
#endif
#if HBM_CP >= 4
    #pragma HLS INTERFACE axis port=out2
    #pragma HLS INTERFACE axis port=out3
#endif
#if HBM_CP >= 8
    #pragma HLS INTERFACE axis port=out4
    #pragma HLS INTERFACE axis port=out5
    #pragma HLS INTERFACE axis port=out6
    #pragma HLS INTERFACE axis port=out7
#endif
    #pragma HLS INTERFACE s_axilite port=index
    #pragma HLS INTERFACE s_axilite port=return

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
        index, out0
#if HBM_CP >= 2
        , out1
#endif
#if HBM_CP >= 4
        , out2, out3
#endif
#if HBM_CP >= 8
        , out4, out5, out6, out7
#endif
        );
}
