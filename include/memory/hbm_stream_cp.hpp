/**
 * @file hbm_stream_cp.hpp   (Memory -- device study)
 * @brief FUNCTION: stream_one -- one independent off-chip read engine.
 *
 *        The class-parallel gather is built by INSTANTIATING THIS ONCE PER
 *        CHANNEL inside a DATAFLOW region, not by writing one loop that issues
 *        all HBM_CP loads together. That distinction is the whole point:
 *
 *          one shared loop  ->  all channels advance in lockstep, so a stall on
 *                               any single HBM pseudo-channel stalls every
 *                               other channel with it.
 *          one engine each  ->  each channel runs at its own rate against its
 *                               own memory controller; a bank conflict or a
 *                               refresh on channel 3 costs channel 3 only.
 *
 *        Under csynth the two are indistinguishable, because csynth models
 *        DRAM as a zero-latency SRAM and never stalls. On the real card they
 *        are not remotely the same, which is why this study runs on hardware.
 *
 *   Knobs:  HBM_WBITS = AXI port width in bits (512 on U280).
 *           HBM_CP    = number of parallel channels. Changes port arity, so it
 *                       is a build macro, not a template parameter.
 *
 *   Contract: (bank, n_words) -> n_words packed wide words on `out`.
 *
 *   NOTE ON DATATYPES. This engine moves packed HBM_WBITS-bit words and never
 *   interprets an element. Bits-per-element therefore does NOT change the
 *   hardware -- it only changes how many bytes a prototype occupies, and hence
 *   how many words must be read for a given class count. binary / int8 / int32
 *   are runtime accounting on this datapath, not separate builds. The
 *   consumer's datatype-dependent cost is deliberately out of scope here; see
 *   the sink in the kernel files.
 */
#ifndef HDC_HBM_STREAM_CP_HPP
#define HDC_HBM_STREAM_CP_HPP

#include <ap_int.h>
#include <hls_stream.h>

#ifndef HBM_WBITS
#define HBM_WBITS 512
#endif
#ifndef HBM_CP
#define HBM_CP 8
#endif

// Words per burst-sized tile. 64 x 64B = 4 KB, which is the AXI maximum burst
// length. The buffered baseline loads exactly one tile at a time, so it is not
// penalised on burst length relative to the streaming design -- the only
// structural difference between the two remains the barrier.
#ifndef HBM_TILE
#define HBM_TILE 64
#endif

// Streaming FIFO depth, in wide words. Must exceed the memory system's
// latency-bandwidth product for run-ahead to absorb a stall: U280 HBM read
// latency is roughly 100-200 ns, which at 300 MHz and one word per cycle is
// 30-60 words. 512 leaves margin for refresh and row-buffer misses.
#ifndef HBM_FIFO_DEPTH
#define HBM_FIFO_DEPTH 512
#endif

namespace hdc {

typedef ap_uint<HBM_WBITS> hbm_word_t;

// One channel's read engine. Contiguous, so the burst inference is maximal.
static void stream_one(const hbm_word_t *bank, int n_words,
                       hls::stream<hbm_word_t> &out) {
STREAM:
    for (int w = 0; w < n_words; w++) {
        #pragma HLS PIPELINE II=1
        #pragma HLS LOOP_TRIPCOUNT min=640 max=2621440 avg=40960
        out.write(bank[w]);
    }
}

// One channel's consumer. Drains at one word per cycle and folds to a 64-bit
// checksum so the host can verify the transfer actually happened -- without a
// verifiable output the compiler is free to delete the whole read.
static void sink_one(hls::stream<hbm_word_t> &in, int n_words,
                     hls::stream<ap_uint<64> > &res) {
    hbm_word_t acc = 0;
DRAIN:
    for (int w = 0; w < n_words; w++) {
        #pragma HLS PIPELINE II=1
        #pragma HLS LOOP_TRIPCOUNT min=640 max=2621440 avg=40960
        acc ^= in.read();
    }
    ap_uint<64> f = 0;
FOLD:
    for (int k = 0; k < HBM_WBITS / 64; k++) {
        #pragma HLS UNROLL
        f ^= acc.range(64 * k + 63, 64 * k);
    }
    res.write(f);
}

} // namespace hdc

#endif // HDC_HBM_STREAM_CP_HPP
