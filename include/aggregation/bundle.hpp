/**
 * @file bundle.hpp   (Aggregation & Update)
 * @brief FUNCTION: bundle (accumulate)  --  (in : HV, acc : ACC[D]) -> ACC[D].
 *
 *   Contract:      superpose `in` into running accumulator `acc`
 *   App (exposed):  input datatype, accumulator datatype/bits (accumulator_bits),
 *                   hv_dim (D), datatype family
 *   Arch (deferred): dimension_parallelism, feature_parallelism, pipeline_mode
 *
 * Bundling is the "add" of majority voting; the majority itself is applied later
 * by threshold(). Keeping accumulate and threshold separate lets one accumulator
 * serve both the per-sample encode (count = num_features) and the per-class
 * prototype build (count = #samples in class).
 *
 * DATATYPE FAMILY. Bundling is a LINEAR operation, so the element must be in a
 * linear value domain before it is added. For binary/bipolar/fixed/integer the
 * stored element already IS the value, so the accumulate is a plain cast. For
 * pow2 the stored element is an EXPONENT: adding it raw would sum exponents
 * instead of values. pow2 therefore decodes (one shift) before accumulating --
 * which is exactly the "narrow store, wide accumulate" split.
 *
 * NOTE ON PARAMETER ORDER. `Family` is appended LAST here (after DP), unlike
 * bind/threshold where it precedes DP. That is deliberate: existing call sites
 * pass DP as the 4th template argument, and appending keeps them compiling
 * unchanged.
 *
 * NOTE(bipolar): elements are already {-1,+1}, so no remapping is needed.
 *
 * STATUS: implemented + C-sim tested (tb/tb_aggregation.cpp).
 */
#ifndef HDC_BUNDLE_HPP
#define HDC_BUNDLE_HPP

#include "common/hdc_types.hpp"

namespace hdc {

// Per-family "element -> linear value" conversion used before accumulation.
template <typename elem_t, typename acc_t> inline acc_t bundle_val(elem_t v, binary_tag)  { return (acc_t)v; }
template <typename elem_t, typename acc_t> inline acc_t bundle_val(elem_t v, bipolar_tag) { return (acc_t)v; }
template <typename elem_t, typename acc_t> inline acc_t bundle_val(elem_t v, fixed_tag)   { return (acc_t)v; }
template <typename elem_t, typename acc_t> inline acc_t bundle_val(elem_t v, integer_tag) { return (acc_t)v; }
template <typename elem_t, typename acc_t> inline acc_t bundle_val(elem_t v, pow2_tag) {
    return pow2_decode<acc_t>((pow2_t)v);
}

// elem_t = input element datatype, acc_t = accumulator datatype, D = hv_dim.
template <typename elem_t, typename acc_t, int D, int DP = 1, typename Family = binary_tag>
void bundle(const elem_t in[D], acc_t acc[D]) {
    #pragma HLS ARRAY_PARTITION variable=in  type=cyclic factor=DP dim=1
    #pragma HLS ARRAY_PARTITION variable=acc type=cyclic factor=DP dim=1
BUNDLE_LOOP:
    for (int i = 0; i < D; i++) {
        #pragma HLS PIPELINE II=1
        #pragma HLS UNROLL   factor=DP
        acc[i] += bundle_val<elem_t, acc_t>(in[i], Family());
    }
}

} // namespace hdc

#endif // HDC_BUNDLE_HPP
