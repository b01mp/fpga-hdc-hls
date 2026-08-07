/**
 * @file similarity_search_onchip.hpp   (Similarity Search)
 * @brief ON-CHIP batched similarity search -- the capacity-crossover baseline.
 *
 *        This is the design prior FPGA-HDC frameworks actually build: the whole
 *        reference library is resident in on-chip memory and read by index.
 *        Hyle states the assumption outright (HVs in BRAM, single-cycle access,
 *        chosen so memory never enters the measurement); F5-HD and AeneasHDC
 *        keep class hypervectors in BRAM the same way.
 *
 *        It is a MIRROR of similarity_search_stream_dt.hpp: identical metric
 *        dispatch, identical query batching, identical 512-bit packed word
 *        layout, identical accumulator structure. The ONLY difference is where
 *        a reference word comes from -- an on-chip array here, a FIFO fed by an
 *        m_axi master there. That is what makes the comparison isolate the
 *        memory tier and nothing else.
 *
 *          binary_tag  : reference is 1-bit. Hamming distance, argmin.
 *                        E = WBITS dims per word, WPR = D/WBITS.
 *          integer_tag : reference is X-bit signed. Dot product, argmax.
 *                        Query is binary, so the product is a conditional
 *                        add/subtract -- no multiplier.
 *                        E = WBITS/X dims per word, WPR = D*X/WBITS.
 *
 *   Contract:      (codebook array, query array) -> QB result tokens
 *   App (exposed):  hv_dim (D), references (NP), datatype family, element width
 *   Arch (deferred): query batch QB, memory tier, banking
 */
#ifndef HDC_SIMILARITY_SEARCH_ONCHIP_HPP
#define HDC_SIMILARITY_SEARCH_ONCHIP_HPP

#include <ap_int.h>
#include "common/hdc_types.hpp"
#include "search/similarity_search_stream_dt.hpp"   // dt_word_t, sim_res_t

namespace hdc {

// ------------------------------------------------------------------------------
// BINARY path: Hamming distance, argmin. Reference word = WBITS binary dims.
// ------------------------------------------------------------------------------
template <int D, int NP, int QB>
void sim_onchip_hamming(const dt_word_t *codebook, int start,
                        const dt_word_t *qin, sim_res_t out[QB]) {
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
        q[i / WPR][i % WPR] = qin[i];
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
            dt_word_t x = codebook[(start + k) * WPR + w];   // <-- array, not stream
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
        #pragma HLS UNROLL
        out[b].score = best_d[b];
        out[b].idx   = best_k[b];
    }
}

// ------------------------------------------------------------------------------
// INTEGER path: dot product, argmax. Reference word = WBITS/X signed X-bit dims.
// Binary query selects sign: score += q ? +ref : -ref (no multiplier).
// ------------------------------------------------------------------------------
template <int D, int NP, int QB, int X>
void sim_onchip_dot(const dt_word_t *codebook, int start,
                    const dt_word_t *qin, sim_res_t out[QB]) {
    static_assert(D % HBM_WBITS == 0, "D must be a multiple of the word width");
    static_assert(HBM_WBITS % X == 0, "WBITS must divide by element width X");
    const int WPR_Q = D / HBM_WBITS;      // query words (binary)
    const int E     = HBM_WBITS / X;      // reference dims per word
    const int WPR_R = D / E;              // reference words = D*X/WBITS
    const int CPW   = HBM_WBITS / E;      // query chunks per query word

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
            dt_word_t x = qin[b * WPR_Q + w];
            for (int c = 0; c < CPW; c++) {
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
            dt_word_t x = codebook[(start + k) * WPR_R + w];   // <-- array, not stream
        QUERY:
            for (int b = 0; b < QB; b++) {
                #pragma HLS UNROLL
                ap_int<48> s = 0;
                ap_uint<E> qw = qc[b][w];
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
        #pragma HLS UNROLL
        out[b].score = best[b];
        out[b].idx   = best_k[b];
    }
}

// ------------------------------------------------------------------------------
// Tag-dispatched wrapper, mirroring similarity_search_stream_dt.
// ------------------------------------------------------------------------------
template <int D, int NP, int QB, int X>
void similarity_search_onchip(const dt_word_t *codebook, int start,
                              const dt_word_t *qin, sim_res_t out[QB],
                              binary_tag) {
    sim_onchip_hamming<D, NP, QB>(codebook, start, qin, out);
}
template <int D, int NP, int QB, int X>
void similarity_search_onchip(const dt_word_t *codebook, int start,
                              const dt_word_t *qin, sim_res_t out[QB],
                              integer_tag) {
    sim_onchip_dot<D, NP, QB, X>(codebook, start, qin, out);
}

} // namespace hdc

#endif // HDC_SIMILARITY_SEARCH_ONCHIP_HPP
