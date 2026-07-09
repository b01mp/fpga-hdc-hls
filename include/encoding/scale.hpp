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
 * STATUS: implemented; C-sim pending.
 */
#ifndef HDC_SCALE_HPP
#define HDC_SCALE_HPP

#include "common/hdc_types.hpp"

namespace hdc {

// elem_t = element datatype, w_t = weight datatype, D = hv_dim.
template <typename elem_t, typename w_t, int D, int DP = 1>
void scale(const elem_t in[D], w_t w, elem_t out[D]) {
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
