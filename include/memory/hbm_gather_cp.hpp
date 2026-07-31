/**
 * @file hbm_gather_cp.hpp   (Memory)
 * @brief FUNCTION: hbm_gather_cp -- class-parallel streaming off-chip read. The
 *        hypervector set is striped across HBM_CP channels; each channel owns one
 *        off-chip array. This primitive streams row `index` of EACH channel (i.e.
 *        HBM_CP different hypervectors) as D/HBM_WBITS packed words into HBM_CP
 *        independent output streams. Channels run in parallel and never interact.
 *
 *        Sits inside a DATAFLOW region: the HBM_CP read engines feed HBM_CP deep
 *        FIFOs (declared in the top), decoupling bursty DRAM from the consumer.
 *        It streams WIDE packed words -- the consumer unpacks per its datatype.
 *
 *   Knobs:  HBM_WBITS = AXI/HBM port width in bits (512 default, U280-friendly).
 *           HBM_CP    = number of parallel channels (= class-parallelism factor).
 *                       Changes port arity, so it is a build macro, not a template.
 *
 *   Contract: (banks, index) -> HBM_CP streams, each of D/HBM_WBITS packed words.
 */
#ifndef HDC_HBM_GATHER_CP_HPP
#define HDC_HBM_GATHER_CP_HPP

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

// N = hypervectors per channel (address space), D = hv_dim in bits.
template <int N, int D>
void hbm_gather_cp(
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
        int index,
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
    int base = index * WPR;

    // One pipelined loop issues HBM_CP independent loads per cycle (one per
    // channel/bundle) and pushes each to its own stream -> HBM_CP prototypes
    // stream in parallel, each over WPR cycles.
STREAM:
    for (int w = 0; w < WPR; w++) {
        #pragma HLS PIPELINE II=1
        out0.write(bank0[base + w]);
#if HBM_CP >= 2
        out1.write(bank1[base + w]);
#endif
#if HBM_CP >= 4
        out2.write(bank2[base + w]);
        out3.write(bank3[base + w]);
#endif
#if HBM_CP >= 8
        out4.write(bank4[base + w]);
        out5.write(bank5[base + w]);
        out6.write(bank6[base + w]);
        out7.write(bank7[base + w]);
#endif
    }
}

} // namespace hdc

#endif // HDC_HBM_GATHER_CP_HPP
