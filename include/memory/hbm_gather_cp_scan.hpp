/**
 * @file hbm_gather_cp_scan.hpp   (Memory)
 * @brief FUNCTION: hbm_gather_cp_scan -- class-parallel streaming off-chip read
 *        that scans NP consecutive prototypes per call instead of one.
 *
 *        Builds directly on hbm_gather_cp.hpp (the design behind
 *        top_hbm_gather_cp_df.cpp): same HBM_WBITS-bit wide words, same HBM_CP
 *        independent channels with one m_axi master each, same single pipelined
 *        II=1 loop, same contiguous addressing so the tool infers bursts. The
 *        only change is an outer prototype loop: one call streams
 *        NP x (D / HBM_WBITS) words per channel, prototype after prototype,
 *        with no gap between them.
 *
 *        WHY: query batching (Direction A). Similarity search compares EVERY
 *        query against EVERY prototype, so the natural fetch granularity is the
 *        whole prototype set, not one row. A consumer that holds a batch of
 *        queries on chip can then serve the whole batch from a single scan,
 *        dividing off-chip traffic per query by the batch size.
 *
 *   Knobs:  HBM_WBITS = AXI/HBM port width in bits (512 default).
 *           HBM_CP    = number of parallel channels (build macro, port arity).
 *
 *   Contract: (banks, start, NP) -> HBM_CP streams, each carrying
 *             NP * D/HBM_WBITS packed words (prototypes start..start+NP-1).
 */
#ifndef HDC_HBM_GATHER_CP_SCAN_HPP
#define HDC_HBM_GATHER_CP_SCAN_HPP

#include <ap_int.h>
#include <hls_stream.h>
#include "common/hdc_types.hpp"

#ifndef HBM_WBITS
#define HBM_WBITS 512
#endif
#ifndef HBM_CP
#define HBM_CP 8
#endif

namespace hdc {

typedef ap_uint<HBM_WBITS> hbm_word_t;

// N = hypervectors per channel (address space), D = hv_dim in bits,
// NP = prototypes scanned per call.
template <int N, int D, int NP>
void hbm_gather_cp_scan(
        const hbm_word_t *bank0,
#if HBM_CP >= 2
        const hbm_word_t *bank1,
#endif
#if HBM_CP >= 4
        const hbm_word_t *bank2, const hbm_word_t *bank3,
#endif
#if HBM_CP >= 8
        const hbm_word_t *bank4, const hbm_word_t *bank5,
        const hbm_word_t *bank6, const hbm_word_t *bank7,
#endif
        int start,
        hls::stream<hbm_word_t> &out0
#if HBM_CP >= 2
        , hls::stream<hbm_word_t> &out1
#endif
#if HBM_CP >= 4
        , hls::stream<hbm_word_t> &out2, hls::stream<hbm_word_t> &out3
#endif
#if HBM_CP >= 8
        , hls::stream<hbm_word_t> &out4, hls::stream<hbm_word_t> &out5
        , hls::stream<hbm_word_t> &out6, hls::stream<hbm_word_t> &out7
#endif
        ) {
    static_assert(D % HBM_WBITS == 0, "D must be a multiple of HBM_WBITS");
    const int WPR = D / HBM_WBITS;      // packed words per hypervector
    int base = start * WPR;

    // Flattened prototype x word loop: one address stream per channel, fully
    // contiguous across the whole scan, pipelined at II=1 -- so the NP
    // prototypes arrive back to back as one long burst per channel.
SCAN:
    for (int i = 0; i < NP * WPR; i++) {
        #pragma HLS PIPELINE II=1
        out0.write(bank0[base + i]);
#if HBM_CP >= 2
        out1.write(bank1[base + i]);
#endif
#if HBM_CP >= 4
        out2.write(bank2[base + i]);
        out3.write(bank3[base + i]);
#endif
#if HBM_CP >= 8
        out4.write(bank4[base + i]);
        out5.write(bank5[base + i]);
        out6.write(bank6[base + i]);
        out7.write(bank7[base + i]);
#endif
    }
}

} // namespace hdc

#endif // HDC_HBM_GATHER_CP_SCAN_HPP
