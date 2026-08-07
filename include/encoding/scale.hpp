/**
 * @file scale.hpp   (Encoding)
 * @brief FUNCTION: scale  --  (in : HV, w : scalar) -> HV  (element-wise weight).
 *
 *   Contract:      (in, w) -> out, same datatype as input
 *   App (exposed):  - (element datatype inherited), hv_dim (D)
 *   Arch (deferred): dimension_parallelism, pipeline_mode
 *
 * Multiplies every element by a scalar weight (weighted bundling / attention).
 *
 * POW2 IS NOT SUPPORTED (see the static_assert). Scaling a signed power of two
 * by an ARBITRARY weight leaves the family -- the result is not a power of two.
 * It is only closed when w is itself a power of two, in which case the operation
 * is an exponent add and belongs in bind(), not here.
 *
 * STATUS: implemented; C-sim pending.
 */
#ifndef HDC_SCALE_HPP
#define HDC_SCALE_HPP

#include "common/hdc_types.hpp"

namespace hdc {

// elem_t = element datatype, w_t = weight datatype, D = hv_dim.
// Family is carried only to reject pow2 at compile time.
template <typename elem_t, typename w_t, int D, int DP = 1,
          typename Family = binary_tag>
void scale(const elem_t in[D], w_t w, elem_t out[D]) {
    static_assert(!is_pow2_family<Family>::value,
        "scale() does not support pow2_tag: multiplying a signed power of two by "
        "an arbitrary weight leaves the family. If w is itself a power of two, "
        "the operation is an exponent add -- use bind() instead.");
    #pragma HLS ARRAY_PARTITION variable=in  type=cyclic factor=DP dim=1
    #pragma HLS ARRAY_PARTITION variable=out type=cyclic factor=DP dim=1
SCALE_LOOP:
    for (int i = 0; i < D; i++) {
        #pragma HLS PIPELINE II=1
        #pragma HLS UNROLL   factor=DP
        out[i] = (elem_t)(in[i] * w);
    }
}

} // namespace hdc

#endif // HDC_SCALE_HPP
