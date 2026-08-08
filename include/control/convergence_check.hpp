/**
 * @file convergence_check.hpp   (Control)
 * @brief FUNCTION: convergence_check  --  (new, old) -> stop : bool.
 *
 *   Contract:      (new[K][D], old[K][D]) -> stop
 *   App (exposed):  num_prototypes (K)   (+ template: convergence_threshold)
 *   Arch (deferred): dimension_parallelism, class_parallelism
 *
 * Stops an iterative (clustering / retraining) loop when the prototype state
 * stops changing. Baseline: total element mismatch count across all K*D elements
 * <= threshold (absolute count).
 *
 * STATUS: skeleton -- baseline mismatch-count body; C-sim pending.
 */
#ifndef HDC_CONVERGENCE_CHECK_HPP
#define HDC_CONVERGENCE_CHECK_HPP

#include "common/hdc_types.hpp"

namespace hdc {

// proto_t = prototype datatype, K = num_prototypes, D = hv_dim.
// threshold = max allowed changed-element count to declare convergence.
template <typename proto_t, int K, int D, int DP = 1, int CP = 1>
bool convergence_check(const proto_t nw[K][D], const proto_t old[K][D],
                       long threshold = 0) {
    #pragma HLS ARRAY_PARTITION variable=nw  type=cyclic factor=CP dim=1
    #pragma HLS ARRAY_PARTITION variable=old type=cyclic factor=CP dim=1
    #pragma HLS ARRAY_PARTITION variable=nw  type=cyclic factor=DP dim=2
    #pragma HLS ARRAY_PARTITION variable=old type=cyclic factor=DP dim=2
    // ---- STRUCTURE NOTE: see similarity_search.hpp for the full argument ---
    //
    // This function had the same defect as similarity_search: UNROLL factor=CP
    // on an OUTER loop wrapping a PIPELINE'd inner loop. Vitis replicates the
    // datapath and then runs the copies in sequence, so CP bought area and no
    // throughput. On the legacy sweep it was worse than useless -- CP 1 -> 8
    // measured 0.61x speedup (i.e. SLOWER) for 5.1x the LUTs.
    //
    // It also had a defect of its own that similarity_search did not: a SINGLE
    // shared `changed` counter incremented inside the innermost loop. Every
    // replicated lane had to read-modify-write the same accumulator, which is a
    // loop-carried dependency across all of them. That is almost certainly why
    // this primitive got actively slower with CP while similarity merely
    // stagnated -- the counter serialised what the unroll had duplicated.
    //
    // Both are fixed the same way: interchange the loops so the DIMENSION loop
    // is the pipelined one, unroll the CLASS loop inside it, and give every
    // lane a PRIVATE counter. The per-lane counts are summed once at the end,
    // outside the hot loop.
    //
    // BEHAVIOUR IS UNCHANGED -- the total is the same set of element
    // comparisons, merely accumulated in CP partial sums first. Addition of the
    // mismatch counts is associative, so the grouping does not affect the
    // result. At CP=1 this is the original single-counter schedule.

    long changed_lane[CP];
    #pragma HLS ARRAY_PARTITION variable=changed_lane complete dim=1

LANE_INIT:
    for (int p = 0; p < CP; p++) {
        #pragma HLS UNROLL
        changed_lane[p] = 0;
    }

CONV_ROW_GROUP:
    for (int kb = 0; kb < K; kb += CP) {
    CONV_COL:
        for (int i = 0; i < D; i++) {
            #pragma HLS PIPELINE II=1
            #pragma HLS UNROLL   factor=DP
        CONV_LANE:
            for (int p = 0; p < CP; p++) {
                #pragma HLS UNROLL
                int k = kb + p;
                if (k < K && nw[k][i] != old[k][i]) changed_lane[p]++;
            }
        }
    }

    long changed = 0;
LANE_REDUCE:
    for (int p = 0; p < CP; p++) {
        #pragma HLS UNROLL
        changed += changed_lane[p];
    }
    return changed <= threshold;
}

} // namespace hdc

#endif // HDC_CONVERGENCE_CHECK_HPP
