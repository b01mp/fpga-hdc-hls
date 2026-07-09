/**
 * @file flatten.hpp   (Encoding)
 * @brief FUNCTION: flatten  --  (in : HM) -> HV  (reshape to vector).
 *
 *   Contract:      (in[R][C]) -> out[R*C]   (row-major)
 *   App (exposed):  - (datatype inherited)
 *   Arch (deferred): pipeline_mode
 *
 * STATUS: implemented; C-sim pending.
 */
#ifndef HDC_FLATTEN_HPP
#define HDC_FLATTEN_HPP

#include "common/hdc_types.hpp"

namespace hdc {

// elem_t = element datatype. out[R*C] = row-major flatten of in[R][C].
template <typename elem_t, int R, int C, int DP = 1>
void flatten(const elem_t in[R][C], elem_t out[R * C]) {
    #pragma HLS ARRAY_PARTITION variable=in  type=cyclic factor=DP dim=2
    #pragma HLS ARRAY_PARTITION variable=out type=cyclic factor=DP dim=1
FLATTEN_ROW:
    for (int r = 0; r < R; r++)
    FLATTEN_COL:
        for (int c = 0; c < C; c++) {
            #pragma HLS PIPELINE II=1
            #pragma HLS UNROLL   factor=DP
            out[r * C + c] = in[r][c];
        }
}

} // namespace hdc

#endif // HDC_FLATTEN_HPP
