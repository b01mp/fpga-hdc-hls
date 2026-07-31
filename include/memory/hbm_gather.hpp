/**
 * @file hbm_gather.hpp   (Memory)
 * @brief FUNCTION: hbm_gather -- streaming off-chip codebook read. Burst-reads
 *        row `index` of an [N][D] binary codebook stored off-chip (packed
 *        HBM_WBITS bits per word) and pushes the row's words into an output FIFO,
 *        so a downstream module (bind / bundle / MAC / ...) can pull + unpack them.
 *
 *        Designed to sit inside a `#pragma HLS DATAFLOW` region: this producer and
 *        the consumer run concurrently, decoupled by a deep FIFO, so bursty DRAM
 *        traffic never stalls the compute stage (HERA / Nystrom-style streaming).
 *        It streams WIDE words (not unpacked bits) -- the consumer unpacks
 *        HBM_WBITS elements per cycle across its own lanes, which is what keeps the
 *        memory port fully utilised and avoids a serial per-bit drain.
 *
 *   Knobs:  HBM_WBITS = AXI/HBM port width in bits. 256 default (U280-friendly);
 *                       set 512 for wider ports, or the NATIVE width of any target
 *                       FPGA -- the design is portable, this is just a knob.
 *           (num_read_outstanding / burst length are set on the m_axi port in the
 *            top wrapper, since interface options live at the top level.)
 *
 *   Contract: (codebook, index) -> stream of D/HBM_WBITS packed words (one HV row).
 *   Note: hbm_gather is datatype-agnostic -- it moves packed bits; the consumer
 *         decides how to interpret them (binary / bipolar / fixed / ...).
 */
#ifndef HDC_HBM_GATHER_HPP
#define HDC_HBM_GATHER_HPP

#include <ap_int.h>
#include <hls_stream.h>
#include "common/hdc_types.hpp"

#ifndef HBM_WBITS
#define HBM_WBITS 256          // native port width; override per target FPGA
#endif

namespace hdc {

typedef ap_uint<HBM_WBITS> hbm_word_t;

// N = codebook rows (address space), D = hv_dim in bits. D must be a multiple of
// HBM_WBITS so a row is a whole number of wide words.
template <int N, int D>
void hbm_gather(const hbm_word_t *codebook, int index, hls::stream<hbm_word_t> &out) {
    static_assert(D % HBM_WBITS == 0, "D must be a multiple of HBM_WBITS");
    const int WPR = D / HBM_WBITS;        // packed words per hypervector row
    int base = index * WPR;
READ:
    for (int w = 0; w < WPR; w++) {
        #pragma HLS PIPELINE II=1
        out.write(codebook[base + w]);    // contiguous wide burst -> deep FIFO
    }
}

} // namespace hdc

#endif // HDC_HBM_GATHER_HPP
