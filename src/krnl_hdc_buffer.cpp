/**
 * @file krnl_hdc_buffer.cpp
 * @brief THE BASELINE. Classes are fetched in parallel from HBM into on-chip
 *        buffers, and only once a buffer is full is it consumed. Fetch and
 *        consume are separated by a barrier, so off-chip latency is exposed
 *        rather than hidden.
 *
 *        This is a competent baseline, not a strawman. It matches the design
 *        (src/krnl_hdc_stream.cpp) on every axis that could otherwise explain
 *        a difference:
 *
 *          same 512-bit wide AXI words, never element-at-a-time
 *          same HBM_CP independent m_axi masters, one HBM channel each
 *          same num_read_outstanding=32, max_read_burst_length=64
 *          same BURST-SIZED TILE (HBM_TILE = 64 words = 4 KB = the AXI maximum
 *              burst length), so it is not handicapped on burst length
 *          same per-channel compute -- XOR fold then 64-bit parity
 *          same top-level interface and the same verifiable checksum output
 *
 *        The single structural difference is the barrier. It is SINGLE
 *        buffered by design: it does not ping-pong, so the next tile's fetch
 *        cannot begin until the current tile has been consumed. That is the
 *        variable under test, and the paper describes this baseline precisely
 *        as "a single-buffered burst loader with per-class channels" rather
 *        than as a tuned loader.
 *
 *        Note that the load is one shared loop across channels, so channels
 *        advance in lockstep. That is inherent to a single-buffered sequential
 *        structure -- decoupling the channels requires the concurrent
 *        processes that define the streaming design.
 *
 *   Build: v++ -c -k krnl_hdc_buffer -D HBM_CP=<1|2|4|8> -D HBM_WBITS=512
 */
#include <ap_int.h>
#include "memory/hbm_stream_cp.hpp"

using hdc::hbm_word_t;

static ap_uint<64> fold64(hbm_word_t acc) {
    ap_uint<64> f = 0;
FOLD:
    for (int k = 0; k < HBM_WBITS / 64; k++) {
        #pragma HLS UNROLL
        f ^= acc.range(64 * k + 63, 64 * k);
    }
    return f;
}

extern "C" void krnl_hdc_buffer(
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
        ap_uint<64> *out,
        int n_words) {

    #pragma HLS INTERFACE m_axi port=bank0 offset=slave bundle=gmem0 num_read_outstanding=32 max_read_burst_length=64
    #pragma HLS INTERFACE s_axilite port=bank0 bundle=control
#if HBM_CP >= 2
    #pragma HLS INTERFACE m_axi port=bank1 offset=slave bundle=gmem1 num_read_outstanding=32 max_read_burst_length=64
    #pragma HLS INTERFACE s_axilite port=bank1 bundle=control
#endif
#if HBM_CP >= 4
    #pragma HLS INTERFACE m_axi port=bank2 offset=slave bundle=gmem2 num_read_outstanding=32 max_read_burst_length=64
    #pragma HLS INTERFACE s_axilite port=bank2 bundle=control
    #pragma HLS INTERFACE m_axi port=bank3 offset=slave bundle=gmem3 num_read_outstanding=32 max_read_burst_length=64
    #pragma HLS INTERFACE s_axilite port=bank3 bundle=control
#endif
#if HBM_CP >= 8
    #pragma HLS INTERFACE m_axi port=bank4 offset=slave bundle=gmem4 num_read_outstanding=32 max_read_burst_length=64
    #pragma HLS INTERFACE s_axilite port=bank4 bundle=control
    #pragma HLS INTERFACE m_axi port=bank5 offset=slave bundle=gmem5 num_read_outstanding=32 max_read_burst_length=64
    #pragma HLS INTERFACE s_axilite port=bank5 bundle=control
    #pragma HLS INTERFACE m_axi port=bank6 offset=slave bundle=gmem6 num_read_outstanding=32 max_read_burst_length=64
    #pragma HLS INTERFACE s_axilite port=bank6 bundle=control
    #pragma HLS INTERFACE m_axi port=bank7 offset=slave bundle=gmem7 num_read_outstanding=32 max_read_burst_length=64
    #pragma HLS INTERFACE s_axilite port=bank7 bundle=control
#endif
    #pragma HLS INTERFACE m_axi port=out offset=slave bundle=gmemout
    #pragma HLS INTERFACE s_axilite port=out bundle=control
    #pragma HLS INTERFACE s_axilite port=n_words bundle=control
    #pragma HLS INTERFACE s_axilite port=return  bundle=control

    // ---- on-chip tile buffers: one burst-sized tile per channel ----
    // A buffer must be FILLED before it can be READ. That read-after-write
    // dependency on the array is what serialises the two phases; it is the
    // only structural difference from the streaming kernel.
    hbm_word_t buf0[HBM_TILE];
    #pragma HLS bind_storage variable=buf0 type=RAM_2P impl=BRAM
#if HBM_CP >= 2
    hbm_word_t buf1[HBM_TILE];
    #pragma HLS bind_storage variable=buf1 type=RAM_2P impl=BRAM
#endif
#if HBM_CP >= 4
    hbm_word_t buf2[HBM_TILE];
    #pragma HLS bind_storage variable=buf2 type=RAM_2P impl=BRAM
    hbm_word_t buf3[HBM_TILE];
    #pragma HLS bind_storage variable=buf3 type=RAM_2P impl=BRAM
#endif
#if HBM_CP >= 8
    hbm_word_t buf4[HBM_TILE];
    #pragma HLS bind_storage variable=buf4 type=RAM_2P impl=BRAM
    hbm_word_t buf5[HBM_TILE];
    #pragma HLS bind_storage variable=buf5 type=RAM_2P impl=BRAM
    hbm_word_t buf6[HBM_TILE];
    #pragma HLS bind_storage variable=buf6 type=RAM_2P impl=BRAM
    hbm_word_t buf7[HBM_TILE];
    #pragma HLS bind_storage variable=buf7 type=RAM_2P impl=BRAM
#endif

    hbm_word_t acc0 = 0;
#if HBM_CP >= 2
    hbm_word_t acc1 = 0;
#endif
#if HBM_CP >= 4
    hbm_word_t acc2 = 0, acc3 = 0;
#endif
#if HBM_CP >= 8
    hbm_word_t acc4 = 0, acc5 = 0, acc6 = 0, acc7 = 0;
#endif

TILE_LOOP:
    for (int base = 0; base < n_words; base += HBM_TILE) {
        #pragma HLS LOOP_TRIPCOUNT min=10 max=40960 avg=640

        // ---- PHASE 1: burst load one tile on every channel ----
    LOAD:
        for (int t = 0; t < HBM_TILE; t++) {
            #pragma HLS PIPELINE II=1
            buf0[t] = bank0[base + t];
#if HBM_CP >= 2
            buf1[t] = bank1[base + t];
#endif
#if HBM_CP >= 4
            buf2[t] = bank2[base + t];
            buf3[t] = bank3[base + t];
#endif
#if HBM_CP >= 8
            buf4[t] = bank4[base + t];
            buf5[t] = bank5[base + t];
            buf6[t] = bank6[base + t];
            buf7[t] = bank7[base + t];
#endif
        }

        // ---- BARRIER: nothing may be consumed until the tile has landed ----

        // ---- PHASE 2: consume the tile from on-chip ----
    COMPUTE:
        for (int t = 0; t < HBM_TILE; t++) {
            #pragma HLS PIPELINE II=1
            acc0 ^= buf0[t];
#if HBM_CP >= 2
            acc1 ^= buf1[t];
#endif
#if HBM_CP >= 4
            acc2 ^= buf2[t];
            acc3 ^= buf3[t];
#endif
#if HBM_CP >= 8
            acc4 ^= buf4[t];
            acc5 ^= buf5[t];
            acc6 ^= buf6[t];
            acc7 ^= buf7[t];
#endif
        }
    }

    out[0] = fold64(acc0);
#if HBM_CP >= 2
    out[1] = fold64(acc1);
#endif
#if HBM_CP >= 4
    out[2] = fold64(acc2);
    out[3] = fold64(acc3);
#endif
#if HBM_CP >= 8
    out[4] = fold64(acc4);
    out[5] = fold64(acc5);
    out[6] = fold64(acc6);
    out[7] = fold64(acc7);
#endif
}
