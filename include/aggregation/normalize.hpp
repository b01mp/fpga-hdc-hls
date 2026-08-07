/**
 * @file normalize.hpp   (Aggregation & Update)
 * @brief FUNCTION: normalize  --  (in : HV) -> HV  (L2 / scale normalized).
 *
 *   Contract:      (in) -> out, L2 / scale normalized
 *   App (exposed):  input datatype, accumulator datatype, hv_dim (D)
 *   Arch (deferred): dimension_parallelism, pipeline_mode
 *
 * L2 normalization. Meaningful for real/fixed-point elements (cosine pipelines);
 * for a 1-bit binary element normalize is a no-op-ish identity. The norm is
 * computed in a wide/real accumulator, then each element is rescaled.
 *
 * POW2 IS NOT SUPPORTED (see the static_assert). A pow2 element stores an
 * EXPONENT, so `in[i]*in[i]` squares the exponent rather than the value, and
 * dividing by a non-power-of-two norm has no representation in the family.
 * Supporting it would mean decode -> normalise -> re-encode, which discards the
 * whole point (the result is no longer a power of two). Rejecting at compile
 * time beats silently returning wrong numbers.
 *
 * STATUS: skeleton -- baseline L2 body written; REVIEW output-datatype semantics
 * (integer elem_t loses precision on divide) before using in an app.
 */
#ifndef HDC_NORMALIZE_HPP
#define HDC_NORMALIZE_HPP

#include <cmath>
#include "common/hdc_types.hpp"

namespace hdc {

// elem_t = element datatype, acc_t = accumulator datatype for the norm, D = hv_dim.
// Family is carried only to reject pow2 at compile time; the body is family-agnostic.
template <typename elem_t, typename acc_t, int D, int DP = 1,
          typename Family = binary_tag>
void normalize(const elem_t in[D], elem_t out[D]) {
    static_assert(!is_pow2_family<Family>::value,
        "normalize() does not support pow2_tag: elements are exponents, so the "
        "L2 norm and the divide are not representable in the family. Decode to a "
        "linear type first, or use a different family for this stage.");
    #pragma HLS ARRAY_PARTITION variable=in  type=cyclic factor=DP dim=1
    #pragma HLS ARRAY_PARTITION variable=out type=cyclic factor=DP dim=1
    acc_t sumsq = 0;
NORM_ACC:
    for (int i = 0; i < D; i++) {
        #pragma HLS PIPELINE II=1
        sumsq += (acc_t)in[i] * (acc_t)in[i];          // reduction: pipelined, not DP-unrolled (needs a tree, later)
    }
    double norm = std::sqrt((double)sumsq);
    if (norm == 0.0) norm = 1.0;                        // avoid div-by-zero on all-zero HV
NORM_SCALE:
    for (int i = 0; i < D; i++) {
        #pragma HLS PIPELINE II=1
        #pragma HLS UNROLL   factor=DP
        out[i] = (elem_t)((double)in[i] / norm);
    }
}

} // namespace hdc

#endif // HDC_NORMALIZE_HPP
