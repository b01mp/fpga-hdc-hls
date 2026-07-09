/**
 * @file transpose.hpp   (Encoding)
 * @brief FUNCTION: transpose  --  (in : HM) -> HM  (axes reordered).
 *
 *   Contract:      (in[R][C]) -> out[C][R]
 *   App (exposed):  - (datatype inherited)
 *   Arch (deferred): memory_space, banking_factor
 *
 * STATUS: implemented; C-sim pending.
 */
#ifndef HDC_TRANSPOSE_HPP
#define HDC_TRANSPOSE_HPP

#include "common/hdc_types.hpp"

namespace hdc {

// elem_t = element datatype. out[C][R] = in[R][C]^T.
template <typename elem_t, int R, int C, int DP = 1>
void transpose(const elem_t in[R][C], elem_t out[C][R]) {
    #pragma HLS ARRAY_PARTITION variable=in  type=cyclic factor=DP dim=2
    #pragma HLS ARRAY_PARTITION variable=out type=cyclic factor=DP dim=1
TRANSPOSE_ROW:
    for (int r = 0; r < R; r++)
    TRANSPOSE_COL:
        for (int c = 0; c < C; c++) {
            #pragma HLS PIPELINE II=1
            #pragma HLS UNROLL   factor=DP
            out[c][r] = in[r][c];
        }
}

} // namespace hdc

#endif // HDC_TRANSPOSE_HPP
