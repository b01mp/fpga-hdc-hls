/**
 * @file threshold.hpp   (Aggregation & Update)
 * @brief FUNCTION: threshold  --  (acc : ACC[D], count) -> HV  (majority / sign).
 *
 *   Contract:      collapse integer accumulator to prototype HV by majority
 *   App (exposed):  prototype datatype, accumulator datatype, threshold_tie, hv_dim (D)
 *   Arch (deferred): dimension_parallelism, pipeline_mode
 *
 * Datatype-parametric (Novelty 1): the collapse op is selected at COMPILE time by
 * a family tag -- majority vote (binary), sign (bipolar), or passthrough/keep-value
 * (fixed/integer/pow2, which are NOT binarized: the bundled prototype stays multi-
 * valued). `count`/`tie` are only used by the binary/bipolar paths.
 *
 * STATUS: datatype-parametric (binary/bipolar/fixed/integer/pow2) + C-sim tested.
 */
#ifndef HDC_THRESHOLD_HPP
#define HDC_THRESHOLD_HPP

#include "common/hdc_types.hpp"

namespace hdc {

// --- Per-family collapse op (accumulator element -> prototype element) ---
//   binary : majority vote  (set iff element was 1 in > half of `count` HVs)
//   bipolar: sign           (+1 if acc>0, -1 if acc<0, tie by policy)
//   fixed/integer/pow2      : passthrough -- keep the accumulated value (a cast
//                             to elem_t); the prototype stays multi-valued.
template <typename acc_t, typename elem_t>
inline elem_t thresh_op(acc_t acc, int count, tie_policy_t tie, binary_tag) {
    acc_t twice_half = (acc_t)count;               // compare 2*acc vs count
    acc_t two_acc    = acc << 1;
    if (two_acc > twice_half) return (elem_t)1;
    if (two_acc < twice_half) return (elem_t)0;
    return (elem_t)(tie == TIE_SET_ONE ? 1 : 0);
}
template <typename acc_t, typename elem_t>
inline elem_t thresh_op(acc_t acc, int count, tie_policy_t tie, bipolar_tag) {
    if (acc > 0) return (elem_t)1;
    if (acc < 0) return (elem_t)-1;
    return (elem_t)(tie == TIE_SET_ONE ? 1 : -1);
}
template <typename acc_t, typename elem_t>
inline elem_t thresh_op(acc_t acc, int count, tie_policy_t tie, fixed_tag)   { return (elem_t)acc; }
template <typename acc_t, typename elem_t>
inline elem_t thresh_op(acc_t acc, int count, tie_policy_t tie, integer_tag) { return (elem_t)acc; }
template <typename acc_t, typename elem_t>
inline elem_t thresh_op(acc_t acc, int count, tie_policy_t tie, pow2_tag)    { return (elem_t)acc; }

// acc_t = accumulator datatype, elem_t = prototype/output datatype, D = hv_dim,
// Family = datatype-family tag (default binary_tag => majority; callers unchanged).
template <typename acc_t, typename elem_t, int D, typename Family = binary_tag, int DP = 1>
void threshold(const acc_t acc[D], elem_t out[D], int count,
               tie_policy_t tie = TIE_SET_ZERO) {
    #pragma HLS ARRAY_PARTITION variable=acc type=cyclic factor=DP dim=1
    #pragma HLS ARRAY_PARTITION variable=out type=cyclic factor=DP dim=1
THRESH_LOOP:
    for (int i = 0; i < D; i++) {
        #pragma HLS PIPELINE II=1
        #pragma HLS UNROLL   factor=DP
        out[i] = thresh_op<acc_t, elem_t>(acc[i], count, tie, Family());
    }
}


} // namespace hdc

#endif // HDC_THRESHOLD_HPP
