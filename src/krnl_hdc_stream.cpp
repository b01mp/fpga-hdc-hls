/**
 * @file krnl_hdc_stream.cpp
 * @brief THE DESIGN. Classes are fetched in parallel from HBM and STREAMED
 *        on-chip, through a deep per-channel FIFO, into the consuming block.
 *        Fetch and consume run concurrently; nothing waits for a whole
 *        prototype to land before work on it begins.
 *
 *        Structure (all inside one DATAFLOW region):
 *
 *          bank0 -> stream_one -> [FIFO 512] -> sink_one -> res0 --\
 *          bank1 -> stream_one -> [FIFO 512] -> sink_one -> res1 ---> merge -> out
 *            ...                                                   /
 *
 *        Every channel is an INDEPENDENT process. There is no shared loop, so
 *        the channels are not coupled and a stall on one HBM pseudo-channel
 *        does not propagate to the others.
 *
 *        Measured against src/krnl_hdc_buffer.cpp, which differs only in that
 *        it buffers a tile on-chip and waits for it before consuming.
 *
 *        The sink is a one-word-per-cycle checksum, standing in for the real
 *        downstream block (bind / bundle / similarity). It is deliberately
 *        datatype-agnostic: this kernel measures the MEMORY PATH, and the
 *        consumer is modelled as able to keep up. A real int32 similarity
 *        consumer may become the bottleneck before memory does; that is a
 *        separate question and is out of scope for this experiment.
 *
 *   Build: v++ -c -k krnl_hdc_stream -D HBM_CP=<1|2|4|8> -D HBM_WBITS=512
 */
#include <ap_int.h>
#include <hls_stream.h>
#include "memory/hbm_stream_cp.hpp"

using hdc::hbm_word_t;

// Collect the per-channel results and write them out through one port. A
// separate merge stage is required: several DATAFLOW processes may not each
// write the same m_axi interface.
static void merge_res(
        hls::stream<ap_uint<64> > &r0,
#if HBM_CP >= 2
        hls::stream<ap_uint<64> > &r1,
#endif
#if HBM_CP >= 4
        hls::stream<ap_uint<64> > &r2, hls::stream<ap_uint<64> > &r3,
#endif
#if HBM_CP >= 8
        hls::stream<ap_uint<64> > &r4, hls::stream<ap_uint<64> > &r5,
        hls::stream<ap_uint<64> > &r6, hls::stream<ap_uint<64> > &r7,
#endif
        ap_uint<64> *out) {
    out[0] = r0.read();
#if HBM_CP >= 2
    out[1] = r1.read();
#endif
#if HBM_CP >= 4
    out[2] = r2.read();
    out[3] = r3.read();
#endif
#if HBM_CP >= 8
    out[4] = r4.read();
    out[5] = r5.read();
    out[6] = r6.read();
    out[7] = r7.read();
#endif
}

extern "C" void krnl_hdc_stream(
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
#if HBM_CP >= 2
    #pragma HLS INTERFACE m_axi port=bank1 offset=slave bundle=gmem1 num_read_outstanding=32 max_read_burst_length=64
#endif
#if HBM_CP >= 4
    #pragma HLS INTERFACE m_axi port=bank2 offset=slave bundle=gmem2 num_read_outstanding=32 max_read_burst_length=64
    #pragma HLS INTERFACE m_axi port=bank3 offset=slave bundle=gmem3 num_read_outstanding=32 max_read_burst_length=64
#endif
#if HBM_CP >= 8
    #pragma HLS INTERFACE m_axi port=bank4 offset=slave bundle=gmem4 num_read_outstanding=32 max_read_burst_length=64
    #pragma HLS INTERFACE m_axi port=bank5 offset=slave bundle=gmem5 num_read_outstanding=32 max_read_burst_length=64
    #pragma HLS INTERFACE m_axi port=bank6 offset=slave bundle=gmem6 num_read_outstanding=32 max_read_burst_length=64
    #pragma HLS INTERFACE m_axi port=bank7 offset=slave bundle=gmem7 num_read_outstanding=32 max_read_burst_length=64
#endif
    #pragma HLS INTERFACE m_axi port=out offset=slave bundle=gmemout
    #pragma HLS INTERFACE s_axilite port=n_words bundle=control
    #pragma HLS INTERFACE s_axilite port=return  bundle=control

    #pragma HLS DATAFLOW

    hls::stream<hbm_word_t> f0;
    #pragma HLS STREAM variable=f0 depth=HBM_FIFO_DEPTH
    hls::stream<ap_uint<64> > r0;
    #pragma HLS STREAM variable=r0 depth=2
#if HBM_CP >= 2
    hls::stream<hbm_word_t> f1;
    #pragma HLS STREAM variable=f1 depth=HBM_FIFO_DEPTH
    hls::stream<ap_uint<64> > r1;
    #pragma HLS STREAM variable=r1 depth=2
#endif
#if HBM_CP >= 4
    hls::stream<hbm_word_t> f2;
    #pragma HLS STREAM variable=f2 depth=HBM_FIFO_DEPTH
    hls::stream<ap_uint<64> > r2;
    #pragma HLS STREAM variable=r2 depth=2
    hls::stream<hbm_word_t> f3;
    #pragma HLS STREAM variable=f3 depth=HBM_FIFO_DEPTH
    hls::stream<ap_uint<64> > r3;
    #pragma HLS STREAM variable=r3 depth=2
#endif
#if HBM_CP >= 8
    hls::stream<hbm_word_t> f4;
    #pragma HLS STREAM variable=f4 depth=HBM_FIFO_DEPTH
    hls::stream<ap_uint<64> > r4;
    #pragma HLS STREAM variable=r4 depth=2
    hls::stream<hbm_word_t> f5;
    #pragma HLS STREAM variable=f5 depth=HBM_FIFO_DEPTH
    hls::stream<ap_uint<64> > r5;
    #pragma HLS STREAM variable=r5 depth=2
    hls::stream<hbm_word_t> f6;
    #pragma HLS STREAM variable=f6 depth=HBM_FIFO_DEPTH
    hls::stream<ap_uint<64> > r6;
    #pragma HLS STREAM variable=r6 depth=2
    hls::stream<hbm_word_t> f7;
    #pragma HLS STREAM variable=f7 depth=HBM_FIFO_DEPTH
    hls::stream<ap_uint<64> > r7;
    #pragma HLS STREAM variable=r7 depth=2
#endif

    // One producer + one consumer per channel, all concurrent.
    hdc::stream_one(bank0, n_words, f0);
    hdc::sink_one  (f0,    n_words, r0);
#if HBM_CP >= 2
    hdc::stream_one(bank1, n_words, f1);
    hdc::sink_one  (f1,    n_words, r1);
#endif
#if HBM_CP >= 4
    hdc::stream_one(bank2, n_words, f2);
    hdc::sink_one  (f2,    n_words, r2);
    hdc::stream_one(bank3, n_words, f3);
    hdc::sink_one  (f3,    n_words, r3);
#endif
#if HBM_CP >= 8
    hdc::stream_one(bank4, n_words, f4);
    hdc::sink_one  (f4,    n_words, r4);
    hdc::stream_one(bank5, n_words, f5);
    hdc::sink_one  (f5,    n_words, r5);
    hdc::stream_one(bank6, n_words, f6);
    hdc::sink_one  (f6,    n_words, r6);
    hdc::stream_one(bank7, n_words, f7);
    hdc::sink_one  (f7,    n_words, r7);
#endif

    merge_res(r0,
#if HBM_CP >= 2
              r1,
#endif
#if HBM_CP >= 4
              r2, r3,
#endif
#if HBM_CP >= 8
              r4, r5, r6, r7,
#endif
              out);
}
