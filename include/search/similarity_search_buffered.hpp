/**
 * @file similarity_search_buffered.hpp   (Similarity Search)
 * @brief BUFFERED (no-overlap) BASELINE for the batched streaming search.
 *
 *        Identical to similarity_search_stream_dt.hpp on every axis that could
 *        otherwise explain a difference:
 *          - same wide HBM_WBITS-bit contiguous burst reads, same AXI tuning
 *          - same D, same NP reference scan, same QB resident query batch
 *          - same metrics: Hamming/argmin (binary), dot/argmax (integer), with
 *            the same chunk-packed binary query and conditional add/subtract
 *
 *        The ONE difference: each reference is first burst-loaded into an
 *        on-chip buffer, then a BARRIER, then the compute runs from that buffer.
 *        Fetch and compute are therefore SERIALIZED -- per reference the design
 *        pays WPR load cycles + WPR compute cycles, where the streaming version
 *        pays max(WPR, WPR) because a deep FIFO lets the producer and consumer
 *        run concurrently inside a DATAFLOW region.
 *
 *        This isolates the fetch/compute overlap in the BioHD setting. Note the
 *        baseline is NOT a strawman: it still gets wide bursts, outstanding
 *        reads, query batching and the real metric -- only the coupling changes.
 *        One reference is buffered at a time (buffering the whole scan would
 *        need NP x 40KB for int32, which is not a realistic design point).
 */
#ifndef HDC_SIMILARITY_SEARCH_BUFFERED_HPP
#define HDC_SIMILARITY_SEARCH_BUFFERED_HPP

#include <ap_int.h>
#include "common/hdc_types.hpp"
#include "search/similarity_search_stream_dt.hpp"   // dt_word_t, sim_res_t

namespace hdc {

// ------------------------------------------------------------------------------
// BINARY: Hamming + argmin, buffered.
// ------------------------------------------------------------------------------
template <int D, int NP, int QB>
void sim_buffered_hamming(const dt_word_t *bank, int start,
                          const dt_word_t *qin, sim_res_t out[QB]) {
    const int WPR = D / HBM_WBITS;

    dt_word_t q[QB][WPR];
    #pragma HLS ARRAY_PARTITION variable=q complete dim=0
    dt_word_t buf[WPR];                      // ONE reference resident on chip
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
        const int base = (start + k) * WPR;
    LOAD_R:                                   // phase 1: burst load
        for (int w = 0; w < WPR; w++) {
            #pragma HLS PIPELINE II=1
            buf[w] = bank[base + w];
        }
        // ---- BARRIER: nothing may compute until the whole reference lands ----
    COMPUTE:                                  // phase 2: compute from buffer
        for (int w = 0; w < WPR; w++) {
            #pragma HLS PIPELINE II=1
            dt_word_t x = buf[w];
            for (int b = 0; b < QB; b++) {
                #pragma HLS UNROLL
                dt_word_t diff = x ^ q[b][w];
                ap_uint<10> pc = 0;
                for (int i = 0; i < HBM_WBITS; i++) {
                    #pragma HLS UNROLL
                    pc += diff[i];
                }
                dist[b] += pc;
            }
        }
    UPDATE:
        for (int b = 0; b < QB; b++) {
            #pragma HLS UNROLL
            if (dist[b] < best_d[b]) { best_d[b] = dist[b]; best_k[b] = (ap_uint<16>)k; }
            dist[b] = 0;
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
// INTEGER: dot product + argmax, buffered. Binary query -> conditional add/sub.
// ------------------------------------------------------------------------------
template <int D, int NP, int QB, int X>
void sim_buffered_dot(const dt_word_t *bank, int start,
                      const dt_word_t *qin, sim_res_t out[QB]) {
    const int WPR_Q = D / HBM_WBITS;      // query words (binary)
    const int E     = HBM_WBITS / X;      // reference dims per word
    const int WPR_R = D / E;              // reference words
    const int CPW   = HBM_WBITS / E;      // query chunks per query word

    ap_uint<E> qc[QB][WPR_R];             // chunk-packed query (see stream_dt)
    #pragma HLS ARRAY_PARTITION variable=qc complete dim=1
    dt_word_t buf[WPR_R];                 // ONE reference resident on chip
    ap_int<48> acc[QB], best[QB];
    ap_uint<16> best_k[QB];
    #pragma HLS ARRAY_PARTITION variable=acc    complete dim=1
    #pragma HLS ARRAY_PARTITION variable=best   complete dim=1
    #pragma HLS ARRAY_PARTITION variable=best_k complete dim=1

LOAD_Q:
    for (int w = 0; w < QB * WPR_Q; w++) {
        #pragma HLS PIPELINE II=1
        dt_word_t x = qin[w];
        int b  = w / WPR_Q;
        int wq = w % WPR_Q;
        for (int c = 0; c < CPW; c++) {
            #pragma HLS UNROLL
            qc[b][wq * CPW + c] = x.range((c + 1) * E - 1, c * E);
        }
    }
INIT:
    for (int b = 0; b < QB; b++) {
        #pragma HLS UNROLL
        acc[b] = 0; best[b] = -( ap_int<48>(1) << 46 ); best_k[b] = 0;
    }
SCAN:
    for (int k = 0; k < NP; k++) {
        const int base = (start + k) * WPR_R;
    LOAD_R:                                   // phase 1: burst load
        for (int w = 0; w < WPR_R; w++) {
            #pragma HLS PIPELINE II=1
            buf[w] = bank[base + w];
        }
        // ---- BARRIER ----
    COMPUTE:                                  // phase 2: compute from buffer
        for (int w = 0; w < WPR_R; w++) {
            #pragma HLS PIPELINE II=1
            dt_word_t x = buf[w];
            for (int b = 0; b < QB; b++) {
                #pragma HLS UNROLL
                ap_int<48> s = 0;
                ap_uint<E> qw = qc[b][w];
                for (int j = 0; j < E; j++) {
                    #pragma HLS UNROLL
                    ap_int<X> r = (ap_int<X>)x.range((j + 1) * X - 1, j * X);
                    s += qw[j] ? (ap_int<48>)r : (ap_int<48>)(-r);
                }
                acc[b] += s;
            }
        }
    UPDATE:
        for (int b = 0; b < QB; b++) {
            #pragma HLS UNROLL
            if (acc[b] > best[b]) { best[b] = acc[b]; best_k[b] = (ap_uint<16>)k; }
            acc[b] = 0;
        }
    }
EMIT:
    for (int b = 0; b < QB; b++) {
        #pragma HLS UNROLL
        out[b].score = best[b];
        out[b].idx   = best_k[b];
    }
}

// Tag-dispatched wrapper, mirroring similarity_search_stream_dt.
template <int D, int NP, int QB, int X>
void similarity_search_buffered(const dt_word_t *bank, int start,
                                const dt_word_t *qin, sim_res_t out[QB],
                                binary_tag) {
    sim_buffered_hamming<D, NP, QB>(bank, start, qin, out);
}
template <int D, int NP, int QB, int X>
void similarity_search_buffered(const dt_word_t *bank, int start,
                                const dt_word_t *qin, sim_res_t out[QB],
                                integer_tag) {
    sim_buffered_dot<D, NP, QB, X>(bank, start, qin, out);
}

} // namespace hdc

#endif // HDC_SIMILARITY_SEARCH_BUFFERED_HPP
