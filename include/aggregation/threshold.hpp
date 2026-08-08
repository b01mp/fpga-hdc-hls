/**
 * @file threshold.hpp   (Aggregation & Update)
 * @brief FUNCTION: threshold  --  (acc : ACC[D], count) -> HV  (majority / sign).
 *
 *   Contract:      collapse integer accumulator to prototype HV by majority
 *   App (exposed):  prototype datatype, accumulator datatype, threshold_tie, hv_dim (D)
 *   Arch (deferred): dimension_parallelism, pipeline_mode
 *
 * Datatype-parametric (Novelty 1): the collapse op is selected at COMPILE time by
 * a family tag -- majority vote (binary), sign (bipolar), passthrough/keep-value
 * (fixed/integer, which are NOT binarized: the bundled prototype stays multi-
 * valued), or re-quantise to the nearest signed power of two (pow2).
 * `count`/`tie` are only used by the binary/bipolar paths.
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
//   fixed/integer           : passthrough -- keep the accumulated value (a cast
//                             to elem_t); the prototype stays multi-valued.
//   pow2                    : ENCODE -- keep the sign and round |acc| to the
//                             nearest power of two (priority encoder + one
//                             comparator). A passthrough cast would be wrong:
//                             acc holds a linear VALUE, a pow2 element holds an
//                             EXPONENT. This is the narrow-store half of the
//                             "wide accumulate, narrow store" split.
template <typename acc_t, typename elem_t>
inline elem_t thresh_op(acc_t acc, int count, tie_policy_t tie, binary_tag) {
    // Majority vote: set the bit iff the element was 1 in MORE than half of
    // `count` bundled hypervectors, i.e. iff 2*acc > count.
    //
    // WHY THE COMPARISON IS WIDENED FIRST. This previously read
    //
    //     acc_t twice_half = (acc_t)count;
    //     acc_t two_acc    = acc << 1;
    //
    // which computes 2*acc IN acc_t's OWN WIDTH. A bundle accumulator is sized
    // to hold 0..N, so acc can reach N -- and 2*N does not fit. When every one
    // of the N bundled hypervectors agreed on a dimension, acc == N, the shift
    // wrapped to a small value, and the vote returned 0 where it must return 1.
    //
    // Two of the three paper applications were affected:
    //
    //     image classification  N=16, ap_uint<5> (0..31), 2N=32  -> wrapped
    //     genome                N=8,  ap_uint<4> (0..15), 2N=16  -> wrapped
    //     time series           N=6,  ap_uint<4> (0..15), 2N=12  -> ok
    //
    // The failure is silent and data-dependent -- it needs unanimity on a
    // dimension, roughly a 3-in-100,000 event per dimension at N=16 with random
    // inputs -- so it survives casual testing and corrupts a bit of the query
    // hypervector when it does fire.
    //
    // The fix belongs HERE and not in the accumulator width. Requiring callers
    // to carry bits_for(N)+1 would spend an extra flip-flop on every one of D
    // dimensions purely to accommodate one comparison inside this function.
    // Widening only the comparands costs nothing: HLS bounds `a2` by the
    // accumulator's range and infers a correspondingly narrow comparator.
    const long a2 = 2L * (long)acc;
    const long c2 = (long)count;
    if (a2 > c2) return (elem_t)1;
    if (a2 < c2) return (elem_t)0;
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
inline elem_t thresh_op(acc_t acc, int count, tie_policy_t tie, pow2_tag) {
    return (elem_t)pow2_encode<acc_t>(acc);
}

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
