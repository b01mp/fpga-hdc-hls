/**
 * @file similarity_search_stream_dt.hpp   (Similarity Search)
 * @brief DATATYPE-PARAMETRIC batched streaming similarity search. Same stream
 *        contract and query-batching idea as similarity_search_stream.hpp, but
 *        the metric is selected at COMPILE time by a family tag -- so one library
 *        primitive covers both BioHD precision configs:
 *
 *          binary_tag  : reference is 1-bit. Hamming distance (XOR + popcount),
 *                        winner = argmin.  E = WBITS dims per word.
 *          integer_tag : reference is X-bit signed. Dot product, winner = argmax.
 *                        E = WBITS/X dims per word.  Because the BioHD query is
 *                        ALWAYS binary, the dot product needs NO multiplier:
 *                        score += (q_bit ? +ref : -ref)  -- conditional add/sub.
 *
 *        This is the datatype knob the DSE searches for BioHD: binary gives cheap
 *        Hamming but many low-capacity references; X-bit gives a costlier dot
 *        product but few high-capacity references. Both emit the same result
 *        token, so the same argmin/argmax merge and the same composed pipeline
 *        wrap either path unchanged.
 *
 *   Contract:      (query stream, reference word stream) -> QB result tokens
 *   App (exposed):  hv_dim (D), references per scan (NP), datatype family,
 *                   element width X (integer path)
 *   Arch (deferred): query batch QB, channel count CP, port width, dataflow
 *
 *   Query packing (both paths): binary, D bits, WPR_Q = D/WBITS words.
 *   Reference packing: binary -> D/WBITS words; integer -> D*X/WBITS words.
 */
#ifndef HDC_SIMILARITY_SEARCH_STREAM_DT_HPP
#define HDC_SIMILARITY_SEARCH_STREAM_DT_HPP

#include <ap_int.h>
#include <hls_stream.h>
#include "common/hdc_types.hpp"

#ifndef HBM_WBITS
#define HBM_WBITS 512
#endif

namespace hdc {

typedef ap_uint<HBM_WBITS> dt_word_t;

// Result token shared by both metric paths: a signed score (Hamming distance for
// binary, dot product for integer) plus the local reference index. Comparison
// direction (min vs max) is fixed by the family tag at the merge.
struct sim_res_t {
    ap_int<48>  score;
    ap_uint<16> idx;
};

// ------------------------------------------------------------------------------
// BINARY path: Hamming distance, argmin. Reference word = WBITS binary dims.
// ------------------------------------------------------------------------------
template <int D, int NP, int QB>
void sim_stream_hamming(hls::stream<dt_word_t> &queries,
                        hls::stream<dt_word_t> &protos,
                        hls::stream<sim_res_t> &result) {
    static_assert(D % HBM_WBITS == 0, "D must be a multiple of the word width");
    const int WPR = D / HBM_WBITS;

    dt_word_t q[QB][WPR];
    #pragma HLS ARRAY_PARTITION variable=q complete dim=0
    ap_uint<20> dist[QB], best_d[QB];
    ap_uint<16> best_k[QB];
    #pragma HLS ARRAY_PARTITION variable=dist   complete dim=1
    #pragma HLS ARRAY_PARTITION variable=best_d complete dim=1
    #pragma HLS ARRAY_PARTITION variable=best_k complete dim=1

LOAD_Q:
    for (int i = 0; i < QB * WPR; i++) {
        #pragma HLS PIPELINE II=1
        q[i / WPR][i % WPR] = queries.read();
    }
INIT:
    for (int b = 0; b < QB; b++) {
        #pragma HLS UNROLL
        dist[b] = 0; best_d[b] = ~ap_uint<20>(0); best_k[b] = 0;
    }
SCAN:
    for (int k = 0; k < NP; k++) {
    WORDS:
        for (int w = 0; w < WPR; w++) {
            #pragma HLS PIPELINE II=1
            dt_word_t x = protos.read();
        QUERY:
            for (int b = 0; b < QB; b++) {
                #pragma HLS UNROLL
                dt_word_t diff = x ^ q[b][w];
                ap_uint<10> pc = 0;
                for (int i = 0; i < HBM_WBITS; i++) {
                    #pragma HLS UNROLL
                    pc += diff[i];
                }
                ap_uint<20> nd = dist[b] + pc;
                if (w == WPR - 1) {
                    if (nd < best_d[b]) { best_d[b] = nd; best_k[b] = (ap_uint<16>)k; }
                    dist[b] = 0;
                } else {
                    dist[b] = nd;
                }
            }
        }
    }
EMIT:
    for (int b = 0; b < QB; b++) {
        #pragma HLS PIPELINE II=1
        sim_res_t r; r.score = best_d[b]; r.idx = best_k[b];
        result.write(r);
    }
}

// ------------------------------------------------------------------------------
// INTEGER path: dot product, argmax. Reference word = WBITS/X signed X-bit dims.
// Binary query selects sign: score += q ? +ref : -ref (no multiplier).
// ------------------------------------------------------------------------------
template <int D, int NP, int QB, int X>
void sim_stream_dot(hls::stream<dt_word_t> &queries,
                    hls::stream<dt_word_t> &protos,
                    hls::stream<sim_res_t> &result) {
    static_assert(D % HBM_WBITS == 0, "D must be a multiple of the word width");
    static_assert(HBM_WBITS % X == 0, "WBITS must divide by element width X");
    const int WPR_Q = D / HBM_WBITS;      // query words (binary)
    const int E     = HBM_WBITS / X;      // reference dims per word
    const int WPR_R = D / E;              // reference words = D*X/WBITS
    const int CPW   = HBM_WBITS / E;      // query chunks per query word

    // Query held as E-bit CHUNKS indexed by reference word: chunk w holds exactly
    // the E query bits that reference word w needs. Reference word w and query
    // chunk w advance together, so the access is a plain sequential read -- no
    // divide, no variable bit-range extraction, no banked scatter network.
    // (Storing the query as a partitioned bit-array instead makes the flattened
    // SCAN body explode and sends the HLS optimizer into hours of if-conversion.)
    ap_uint<E> qc[QB][WPR_R];
    #pragma HLS ARRAY_PARTITION variable=qc complete dim=1
    ap_int<48> acc[QB], best[QB];
    ap_uint<16> best_k[QB];
    #pragma HLS ARRAY_PARTITION variable=acc    complete dim=1
    #pragma HLS ARRAY_PARTITION variable=best   complete dim=1
    #pragma HLS ARRAY_PARTITION variable=best_k complete dim=1

LOAD_Q:
    for (int b = 0; b < QB; b++) {
        for (int w = 0; w < WPR_Q; w++) {
            #pragma HLS PIPELINE II=1
            dt_word_t x = queries.read();
            for (int c = 0; c < CPW; c++) {      // split one query word into CPW chunks
                #pragma HLS UNROLL
                qc[b][w * CPW + c] = x.range((c + 1) * E - 1, c * E);
            }
        }
    }
INIT:
    for (int b = 0; b < QB; b++) {
        #pragma HLS UNROLL
        acc[b] = 0; best[b] = -( ap_int<48>(1) << 46 ); best_k[b] = 0;
    }
SCAN:
    for (int k = 0; k < NP; k++) {
    WORDS:
        for (int w = 0; w < WPR_R; w++) {
            #pragma HLS PIPELINE II=1
            dt_word_t x = protos.read();
        QUERY:
            for (int b = 0; b < QB; b++) {
                #pragma HLS UNROLL
                ap_int<48> s = 0;
                ap_uint<E> qw = qc[b][w];        // the E query bits for this word
            ELEM:
                for (int j = 0; j < E; j++) {
                    #pragma HLS UNROLL
                    ap_int<X> r = (ap_int<X>)x.range((j + 1) * X - 1, j * X);
                    s += qw[j] ? (ap_int<48>)r : (ap_int<48>)(-r);
                }
                ap_int<48> na = acc[b] + s;
                if (w == WPR_R - 1) {
                    if (na > best[b]) { best[b] = na; best_k[b] = (ap_uint<16>)k; }
                    acc[b] = 0;
                } else {
                    acc[b] = na;
                }
            }
        }
    }
EMIT:
    for (int b = 0; b < QB; b++) {
        #pragma HLS PIPELINE II=1
        sim_res_t r; r.score = best[b]; r.idx = best_k[b];
        result.write(r);
    }
}

// ------------------------------------------------------------------------------
// Tag-dispatched wrapper: one primitive name, metric chosen at compile time.
// Binary ignores X; integer uses it. Winner direction travels with the tag to
// the merge (see argmin/argmax_merge).
// ------------------------------------------------------------------------------
template <int D, int NP, int QB, int X, typename Family>
void similarity_search_stream_dt(hls::stream<dt_word_t> &queries,
                                 hls::stream<dt_word_t> &protos,
                                 hls::stream<sim_res_t> &result,
                                 binary_tag) {
    sim_stream_hamming<D, NP, QB>(queries, protos, result);
}
template <int D, int NP, int QB, int X, typename Family>
void similarity_search_stream_dt(hls::stream<dt_word_t> &queries,
                                 hls::stream<dt_word_t> &protos,
                                 hls::stream<sim_res_t> &result,
                                 integer_tag) {
    sim_stream_dot<D, NP, QB, X>(queries, protos, result);
}

} // namespace hdc

#endif // HDC_SIMILARITY_SEARCH_STREAM_DT_HPP
