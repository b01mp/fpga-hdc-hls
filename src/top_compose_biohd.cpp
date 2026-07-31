/**
 * @file top_compose_biohd.cpp
 * @brief BioHD composed off-chip similarity search, DATATYPE-PARAMETRIC.
 *        Same three-block composition as top_compose_search.cpp
 *          hbm_gather_cp_scan -> similarity_search_stream_dt -> res_merge
 *        but the metric is chosen at compile time so ONE top covers both BioHD
 *        precision configs:
 *
 *          BIO_X = 1  : binary library, Hamming distance, argmin.
 *                       reference = D bits, WPR = D/512 words.
 *          BIO_X = 32 : 32-bit integer library, dot product, argmax.
 *                       reference = 32*D bits, WPR = 32*D/512 words.
 *                       (BioHD's high-precision library is integer counts, and
 *                        the query is always binary, so dot = conditional
 *                        add/subtract -- no multiplier.)
 *
 *        The query is binary in BOTH configs: D bits, D/512 words, broadcast to
 *        every channel. Only compute is in the primitives; the top just wires.
 *
 *        Swept over precision (BIO_X) x prototype count (BIO_NP) x channels
 *        (HBM_CP) by scripts/sweep_biohd.tcl. BioHD anchor: D=10240 (10k padded
 *        to a 512-bit multiple), query length ~200, library = many refs.
 *
 *        Builds on (none modified): hbm_gather_cp_scan.hpp,
 *        similarity_search_stream_dt.hpp, res_merge.hpp.
 */
#include <ap_int.h>
#include <hls_stream.h>
#include "common/hdc_types.hpp"
#include "memory/hbm_gather_cp_scan.hpp"
#include "search/similarity_search_stream_dt.hpp"
#include "search/similarity_search_buffered.hpp"
#include "search/res_merge.hpp"

// BIO_OVERLAP = 1 : streaming, producer + consumer concurrent in a DATAFLOW
//                   region decoupled by a deep per-channel FIFO (the design).
// BIO_OVERLAP = 0 : BASELINE. Per reference, burst-load into an on-chip buffer,
//                   barrier, then compute. Same bursts, same AXI tuning, same
//                   metric, same query batching -- only the coupling changes,
//                   so the delta isolates the fetch/compute overlap.
#ifndef BIO_OVERLAP
#define BIO_OVERLAP 1
#endif

#ifndef BIO_D
#define BIO_D 10240          // hv dimensions (10k padded to a 512-bit multiple)
#endif
#ifndef BIO_X
#define BIO_X 1              // element width: 1 = binary, 32 = int32 library
#endif
#ifndef BIO_NP
#define BIO_NP 64            // reference hypervectors scanned per call
#endif
#ifndef HBM_QB
#define HBM_QB 4             // resident query batch
#endif
#ifndef HBM_OUTSTANDING
#define HBM_OUTSTANDING 16
#endif
#ifndef HBM_FIFO_DEPTH
#define HBM_FIFO_DEPTH 64
#endif

#define REF_BITS (BIO_D * BIO_X)         // reference size in bits
#define WPRQ     (BIO_D / HBM_WBITS)     // query words (binary)

#if BIO_X == 1
typedef hdc::binary_tag  bio_family_t;
#else
typedef hdc::integer_tag bio_family_t;
#endif

// Broadcast the binary query batch to every channel.
static void qsplit(const hdc::dt_word_t qin[HBM_QB * WPRQ],
                   hls::stream<hdc::dt_word_t> qs[HBM_CP]) {
QSPLIT:
    for (int i = 0; i < HBM_QB * WPRQ; i++) {
        #pragma HLS PIPELINE II=1
        hdc::dt_word_t x = qin[i];
        for (int c = 0; c < HBM_CP; c++) {
            #pragma HLS UNROLL
            qs[c].write(x);
        }
    }
}

void compose_biohd_top(
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
        const hdc::dt_word_t qin[HBM_QB * WPRQ],
        int start,
        int out_id[HBM_QB], ap_int<48> out_score[HBM_QB]) {
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
    #pragma HLS INTERFACE ap_memory port=qin
    #pragma HLS INTERFACE s_axilite port=start
    #pragma HLS INTERFACE ap_memory port=out_id
    #pragma HLS INTERFACE ap_memory port=out_score
    #pragma HLS INTERFACE s_axilite port=return
    #pragma HLS ARRAY_PARTITION variable=out_id    complete dim=1
    #pragma HLS ARRAY_PARTITION variable=out_score complete dim=1

#if BIO_OVERLAP == 0
    // ================= BASELINE: buffered, no fetch/compute overlap =========
    // Per reference: burst-load into an on-chip buffer, barrier, then compute.
    // No DATAFLOW region and no FIFO, so the off-chip latency is exposed.
    hdc::sim_res_t r0[HBM_QB];
    #pragma HLS ARRAY_PARTITION variable=r0 complete dim=1
    hdc::similarity_search_buffered<BIO_D, BIO_NP, HBM_QB, BIO_X>(
        bank0, start, qin, r0, bio_family_t());
MERGE_B:
    for (int b = 0; b < HBM_QB; b++) {
        #pragma HLS PIPELINE II=1
        out_id[b]    = (int)r0[b].idx * HBM_CP;
        out_score[b] = r0[b].score;
    }
#else
    // ================= DESIGN: streaming with FIFO overlap ==================
    #pragma HLS DATAFLOW

    hls::stream<hdc::dt_word_t> qs[HBM_CP];
    #pragma HLS STREAM variable=qs depth=4
    hls::stream<hdc::sim_res_t> res[HBM_CP];
    #pragma HLS STREAM variable=res depth=8

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

    // block 0: query broadcast
    qsplit(qin, qs);

    // block 1: memory scan (reference size in BITS = REF_BITS)
    hdc::hbm_gather_cp_scan<BIO_NP, REF_BITS, BIO_NP>(bank0,
#if HBM_CP >= 2
        bank1,
#endif
#if HBM_CP >= 4
        bank2, bank3,
#endif
#if HBM_CP >= 8
        bank4, bank5, bank6, bank7,
#endif
        start, fifo0
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

    // block 2: datatype-parametric batched search (D in DIMS, X = element width)
    hdc::similarity_search_stream_dt<BIO_D, BIO_NP, HBM_QB, BIO_X, bio_family_t>(qs[0], fifo0, res[0], bio_family_t());
#if HBM_CP >= 2
    hdc::similarity_search_stream_dt<BIO_D, BIO_NP, HBM_QB, BIO_X, bio_family_t>(qs[1], fifo1, res[1], bio_family_t());
#endif
#if HBM_CP >= 4
    hdc::similarity_search_stream_dt<BIO_D, BIO_NP, HBM_QB, BIO_X, bio_family_t>(qs[2], fifo2, res[2], bio_family_t());
    hdc::similarity_search_stream_dt<BIO_D, BIO_NP, HBM_QB, BIO_X, bio_family_t>(qs[3], fifo3, res[3], bio_family_t());
#endif
#if HBM_CP >= 8
    hdc::similarity_search_stream_dt<BIO_D, BIO_NP, HBM_QB, BIO_X, bio_family_t>(qs[4], fifo4, res[4], bio_family_t());
    hdc::similarity_search_stream_dt<BIO_D, BIO_NP, HBM_QB, BIO_X, bio_family_t>(qs[5], fifo5, res[5], bio_family_t());
    hdc::similarity_search_stream_dt<BIO_D, BIO_NP, HBM_QB, BIO_X, bio_family_t>(qs[6], fifo6, res[6], bio_family_t());
    hdc::similarity_search_stream_dt<BIO_D, BIO_NP, HBM_QB, BIO_X, bio_family_t>(qs[7], fifo7, res[7], bio_family_t());
#endif

    // block 3: cross-channel reduction (direction from the family tag)
    hdc::res_merge<HBM_CP, HBM_QB>(res, out_id, out_score, bio_family_t());
#endif  // BIO_OVERLAP
}
