/**
 * @file res_merge.hpp   (Similarity Search)
 * @brief FUNCTION: res_merge -- cross-channel reduction for the datatype-
 *        parametric streaming search (sim_res_t tokens). Each channel searched a
 *        disjoint reference stripe and emitted a local winner per query; this
 *        folds the CP local winners into the global winner:
 *            global_id = local_k * CP + channel.
 *
 *        The comparison direction is fixed by the family tag, so the SAME merge
 *        wraps both BioHD precisions: binary -> argmin (nearest Hamming),
 *        integer -> argmax (largest dot product).
 *
 *   Contract:      (CP result streams) -> global (id, score) per query
 *   App (exposed):  queries per batch (QB)
 *   Arch (deferred): channel count CP (instantiation-time)
 */
#ifndef HDC_RES_MERGE_HPP
#define HDC_RES_MERGE_HPP

#include <ap_int.h>
#include <hls_stream.h>
#include "search/similarity_search_stream_dt.hpp"

namespace hdc {

// binary: argmin (nearest Hamming distance)
template <int CP_, int QB>
void res_merge(hls::stream<sim_res_t> res[CP_],
               int out_id[QB], ap_int<48> out_score[QB], binary_tag) {
    sim_res_t tok[CP_][QB];
    #pragma HLS ARRAY_PARTITION variable=tok complete dim=1
COLLECT:
    for (int b = 0; b < QB; b++)
        for (int c = 0; c < CP_; c++) {
            #pragma HLS PIPELINE II=1
            tok[c][b] = res[c].read();
        }
MERGE:
    for (int b = 0; b < QB; b++) {
        #pragma HLS PIPELINE II=1
        ap_int<48> best = tok[0][b].score;
        int gid = (int)tok[0][b].idx * CP_ + 0;
        for (int c = 1; c < CP_; c++) {
            #pragma HLS UNROLL
            if (tok[c][b].score < best) { best = tok[c][b].score; gid = (int)tok[c][b].idx * CP_ + c; }
        }
        out_id[b] = gid; out_score[b] = best;
    }
}

// integer: argmax (largest dot product)
template <int CP_, int QB>
void res_merge(hls::stream<sim_res_t> res[CP_],
               int out_id[QB], ap_int<48> out_score[QB], integer_tag) {
    sim_res_t tok[CP_][QB];
    #pragma HLS ARRAY_PARTITION variable=tok complete dim=1
COLLECT:
    for (int b = 0; b < QB; b++)
        for (int c = 0; c < CP_; c++) {
            #pragma HLS PIPELINE II=1
            tok[c][b] = res[c].read();
        }
MERGE:
    for (int b = 0; b < QB; b++) {
        #pragma HLS PIPELINE II=1
        ap_int<48> best = tok[0][b].score;
        int gid = (int)tok[0][b].idx * CP_ + 0;
        for (int c = 1; c < CP_; c++) {
            #pragma HLS UNROLL
            if (tok[c][b].score > best) { best = tok[c][b].score; gid = (int)tok[c][b].idx * CP_ + c; }
        }
        out_id[b] = gid; out_score[b] = best;
    }
}

} // namespace hdc

#endif // HDC_RES_MERGE_HPP
