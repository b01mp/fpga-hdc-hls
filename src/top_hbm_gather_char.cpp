/**
 * @file top_hbm_gather_char.cpp
 * @brief Characterization top for the streaming hbm_gather. Exposes the primitive's
 *        wide m_axi read + FIFO output directly (as an AXI-Stream) with NO unpack
 *        consumer -- so csynth measures the REAL off-chip streaming access, not the
 *        demo top's array-drain (which is a single-port test artifact). Swept over
 *        HBM_WBITS by scripts/sweep_hbm_gather.tcl.
 */
#include <ap_int.h>
#include <hls_stream.h>
#include "common/hdc_types.hpp"
#include "memory/hbm_gather.hpp"

#define TN 128
#define TD 1024

#ifndef HBM_OUTSTANDING
#define HBM_OUTSTANDING 16
#endif

void hbm_gather_char(const hdc::hbm_word_t *codebook, int index,
                     hls::stream<hdc::hbm_word_t> &out) {
    #pragma HLS INTERFACE m_axi port=codebook offset=slave bundle=gmem0 num_read_outstanding=HBM_OUTSTANDING max_read_burst_length=64
    #pragma HLS INTERFACE axis port=out
    #pragma HLS INTERFACE s_axilite port=index
    #pragma HLS INTERFACE s_axilite port=return

    hdc::hbm_gather<TN, TD>(codebook, index, out);
}
