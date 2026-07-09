/**
 * @file permute.hpp   (Encoding)
 * @brief FUNCTION: permute  --  (in : HV, shift : int) -> HV  (cyclic rotate).
 *
 *   Contract:      (in, shift) -> out, same datatype as input
 *   App (exposed):  encoding_template  (+ template: ngram_size, window_stride define the shift)
 *   Arch (deferred): dimension_parallelism, banking_factor, pipeline_mode
 *
 * Cyclic (rotation) permutation used to encode position/sequence (n-gram). This
 * is the primitive the temporal EMG encoder needs on top of the record baseline.
 *
 * STATUS: implemented (cyclic shift); C-sim pending.
 */
#ifndef HDC_PERMUTE_HPP
#define HDC_PERMUTE_HPP

#include "common/hdc_types.hpp"

namespace hdc {

// elem_t = element datatype, D = hv_dim. Positive shift = rotate toward higher index.
template <typename elem_t, int D, int DP = 1>
void permute(const elem_t in[D], int shift, elem_t out[D]) {
    #pragma HLS ARRAY_PARTITION variable=in  type=cyclic factor=DP dim=1
    #pragma HLS ARRAY_PARTITION variable=out type=cyclic factor=DP dim=1
    int s = ((shift % D) + D) % D;                 // normalize to [0, D)
PERMUTE_LOOP:
    for (int i = 0; i < D; i++) {
        #pragma HLS PIPELINE II=1
        #pragma HLS UNROLL   factor=DP
        int j = (i + s) % D;
        out[j] = in[i];
    }
}

} // namespace hdc

#endif // HDC_PERMUTE_HPP
