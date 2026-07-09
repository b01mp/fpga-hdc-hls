/**
 * @file place.hpp   (Memory)
 * @brief FUNCTION: place / bank  --  (t : tensor) -> tensor  (placement directive).
 *
 *   Contract:      (in[N][D]) -> out[N][D]   (identity on data)
 *   App (exposed):  -
 *   Arch (deferred): memory_space, banking_factor, materialize, target_fpga
 *
 * A placement/banking directive: on the DATA it is the identity. Its real effect
 * is architectural (ARRAY_PARTITION / bind_storage on the tensor), which is a
 * deferred architecture parameter -- so for now this is a pure copy that marks
 * where those pragmas will attach.
 *
 * STATUS: implemented as identity (arch pragmas deferred by directive).
 */
#ifndef HDC_PLACE_HPP
#define HDC_PLACE_HPP

#include "common/hdc_types.hpp"

namespace hdc {

// elem_t = element datatype, N = rows, D = hv_dim, DP = dimension_parallelism.
// Identity on the data; its real effect is the banking directive below.
// (memory_space / bind_storage is a declaration-level decision made in the top
//  wrapper where the tensor actually lives -- added there, not here.)
template <typename elem_t, int N, int D, int DP = 1>
void place(const elem_t in[N][D], elem_t out[N][D]) {
    #pragma HLS ARRAY_PARTITION variable=in  type=cyclic factor=DP dim=2
    #pragma HLS ARRAY_PARTITION variable=out type=cyclic factor=DP dim=2
PLACE_ROW:
    for (int n = 0; n < N; n++)
    PLACE_COL:
        for (int i = 0; i < D; i++) {
            #pragma HLS PIPELINE II=1
            #pragma HLS UNROLL   factor=DP
            out[n][i] = in[n][i];
        }
}

} // namespace hdc

#endif // HDC_PLACE_HPP
