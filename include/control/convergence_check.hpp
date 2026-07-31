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
    long changed = 0;
CONV_ROW:
    for (int k = 0; k < K; k++) {
        #pragma HLS UNROLL factor=CP
    CONV_COL:
        for (int i = 0; i < D; i++) {
            #pragma HLS PIPELINE II=1
            #pragma HLS UNROLL   factor=DP
            if (nw[k][i] != old[k][i]) changed++;
        }
    }
    return changed <= threshold;
}

} // namespace hdc

#endif // HDC_CONVERGENCE_CHECK_HPP
