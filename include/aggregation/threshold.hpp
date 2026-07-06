/**
 * @file threshold.hpp   (Aggregation & Update)
 * @brief FUNCTION: threshold  --  (acc : ACC[D], count) -> HV  (majority / sign).
 *
 *   Contract:      collapse integer accumulator to prototype HV by majority
 *   App (exposed):  prototype datatype, accumulator datatype, threshold_tie, hv_dim (D)
 *   Arch (deferred): dimension_parallelism, pipeline_mode
 *
 * Element is 1 iff it was set in more than half of the `count` bundled HVs.
 * Exact ties (2*acc == count) resolved by the tie policy. Comparison uses
 * 2*acc vs count to avoid a fractional threshold. Ported from emg_hdc; accumulator
 * and output datatypes are now template arguments.
 *
 * STATUS: implemented + C-sim tested (tb/tb_aggregation.cpp).
 */
#ifndef HDC_THRESHOLD_HPP
#define HDC_THRESHOLD_HPP

#include "common/hdc_types.hpp"

namespace hdc {

// acc_t = accumulator datatype, elem_t = prototype/output datatype, D = hv_dim.
template <typename acc_t, typename elem_t, int D>
void threshold(const acc_t acc[D], elem_t out[D], int count,
               tie_policy_t tie = TIE_SET_ZERO) {
    const acc_t twice_half = (acc_t)count;         // threshold on 2*acc
THRESH_LOOP:
    for (int i = 0; i < D; i++) {
        acc_t two_acc = acc[i] << 1;               // 2 * acc[i]
        if (two_acc > twice_half)      out[i] = (elem_t)1;
        else if (two_acc < twice_half) out[i] = (elem_t)0;
        else                           out[i] = (elem_t)(tie == TIE_SET_ONE ? 1 : 0);
    }
}

} // namespace hdc

#endif // HDC_THRESHOLD_HPP
